"""Conformance checking: reference (soll) BPMN vs. actual event log (Story 3.3).

A user uploads a target BPMN model; we replay the recorded event log against it
via PM4Py and report:

* an overall **fitness** score (0..1) — computed with alignments (precise) or
  token-based replay (fast), selectable by the caller;
* **per-case deviations** in plain language ("Activity X is missing", "Activity Y
  is not allowed here", "Activity Z is out of order"), derived from optimal
  alignments so they are exact;
* a **deviation summary** aggregated by activity and sorted by frequency, so the
  UI can filter the most common problems first.

Story 6.2 layers a natural-language explanation on top via :mod:`app.services.ai`.
"""

from __future__ import annotations

import os
import tempfile
from collections import defaultdict
from dataclasses import dataclass

import pm4py
from pm4py.objects.petri_net.obj import Marking, PetriNet
from sqlalchemy.orm import Session

from app.schemas.analysis import (
    CaseDeviation,
    ConformanceReport,
    ConformanceRequest,
    DeviationStat,
)
from app.services.process_data import load_dataframe

_SKIP = ">>"


class ConformanceError(Exception):
    """Raised when the uploaded BPMN cannot be parsed or replayed."""


@dataclass
class _Move:
    kind: str  # 'missing' | 'unexpected'
    activity: str


def _petri_from_bpmn(bpmn_xml: str) -> tuple[PetriNet, Marking, Marking]:
    fd, path = tempfile.mkstemp(suffix=".bpmn")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(bpmn_xml)
        bpmn = pm4py.read_bpmn(path)
    except Exception as exc:  # noqa: BLE001 - uniform error for any parse failure
        raise ConformanceError(f"Could not parse BPMN model: {exc}") from exc
    finally:
        if os.path.exists(path):
            os.remove(path)
    net, im, fm = pm4py.convert_to_petri_net(bpmn)
    if not net.transitions:
        raise ConformanceError("BPMN model has no activities to check against")
    return net, im, fm


def _event_log(db: Session, log_id: str):  # noqa: ANN202 - pm4py EventLog type
    df = load_dataframe(db, log_id)
    if df.empty:
        return None, []
    formatted = pm4py.format_dataframe(
        df,
        case_id="case:concept:name",
        activity_key="concept:name",
        timestamp_key="time:timestamp",
    )
    el = pm4py.convert_to_event_log(formatted)
    case_keys = [str(trace.attributes.get("concept:name")) for trace in el]
    return el, case_keys


def _moves_from_alignment(alignment: list[tuple[object, object]]) -> list[_Move]:
    moves: list[_Move] = []
    for log_label, model_label in alignment:
        if model_label is None:
            continue  # invisible/silent model step
        if log_label == _SKIP and model_label != _SKIP:
            moves.append(_Move("missing", str(model_label)))
        elif model_label == _SKIP and log_label != _SKIP:
            moves.append(_Move("unexpected", str(log_label)))
    return moves


def _describe(moves: list[_Move]) -> tuple[list[str], list[tuple[str, str]]]:
    """Turn raw moves into plain-text lines and (kind, activity) pairs.

    When an activity is both missing and unexpected in the same case it was most
    likely executed out of order, so we collapse the pair into one 'order' entry.
    """
    missing = {m.activity for m in moves if m.kind == "missing"}
    unexpected = {m.activity for m in moves if m.kind == "unexpected"}
    reordered = missing & unexpected

    lines: list[str] = []
    pairs: list[tuple[str, str]] = []
    for act in sorted(reordered):
        lines.append(f"Activity '{act}' is out of order")
        pairs.append(("order", act))
    for act in sorted(missing - reordered):
        lines.append(f"Activity '{act}' is missing (expected by the model)")
        pairs.append(("missing", act))
    for act in sorted(unexpected - reordered):
        lines.append(f"Activity '{act}' is not allowed by the model")
        pairs.append(("unexpected", act))
    return lines, pairs


_DESCRIPTIONS = {
    "missing": "Activity '{a}' is missing (expected by the model)",
    "unexpected": "Activity '{a}' is not allowed by the model",
    "order": "Activity '{a}' is out of order",
}


def check_conformance(
    db: Session, log_id: str, bpmn_xml: str, params: ConformanceRequest
) -> ConformanceReport:
    net, im, fm = _petri_from_bpmn(bpmn_xml)
    el, case_keys = _event_log(db, log_id)

    if el is None:
        return ConformanceReport(
            log_id=log_id,
            method=params.method,
            fitness=0.0,
            fitting_case_count=0,
            case_count=0,
            percentage_fitting=0.0,
            deviation_summary=[],
            case_deviations=[],
        )

    alignments = pm4py.conformance_diagnostics_alignments(el, net, im, fm)

    case_deviations: list[CaseDeviation] = []
    summary_counts: dict[tuple[str, str], int] = defaultdict(int)
    fitting = 0

    for case_key, diag in zip(case_keys, alignments, strict=False):
        moves = _moves_from_alignment(diag.get("alignment") or [])
        lines, pairs = _describe(moves)
        trace_fitness = float(diag.get("fitness", 0.0))
        is_fitting = not pairs
        if is_fitting:
            fitting += 1
        case_deviations.append(
            CaseDeviation(
                case_key=case_key,
                fitness=round(trace_fitness, 4),
                is_fitting=is_fitting,
                deviations=lines,
            )
        )
        seen_in_case: set[tuple[str, str]] = set()
        for kind, act in pairs:
            if (kind, act) not in seen_in_case:
                summary_counts[(kind, act)] += 1
                seen_in_case.add((kind, act))

    deviation_summary = [
        DeviationStat(
            kind=kind,
            activity=act,
            description=_DESCRIPTIONS[kind].format(a=act),
            case_count=count,
        )
        for (kind, act), count in sorted(
            summary_counts.items(), key=lambda kv: (-kv[1], kv[0][1], kv[0][0])
        )
    ]

    fitness = _overall_fitness(el, net, im, fm, params.method)

    case_deviations.sort(key=lambda c: (c.is_fitting, c.fitness, c.case_key))

    report = ConformanceReport(
        log_id=log_id,
        method=params.method,
        fitness=round(fitness, 4),
        fitting_case_count=fitting,
        case_count=len(case_keys),
        percentage_fitting=round(100.0 * fitting / len(case_keys), 2) if case_keys else 0.0,
        deviation_summary=deviation_summary,
        case_deviations=case_deviations,
    )

    if params.explain:
        # Imported lazily to avoid a circular import (ai package -> schemas only).
        from app.services import ai

        report.explanation, report.explanation_source = ai.explain_deviations(report)

    return report


def _overall_fitness(
    el, net: PetriNet, im: Marking, fm: Marking, method: str  # noqa: ANN001
) -> float:
    if method == "token":
        result = pm4py.fitness_token_based_replay(el, net, im, fm)
    else:
        result = pm4py.fitness_alignments(el, net, im, fm)
    return float(result.get("average_trace_fitness", result.get("log_fitness", 0.0)))
