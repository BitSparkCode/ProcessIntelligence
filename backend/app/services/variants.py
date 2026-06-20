"""Variant analysis (Story 2.4).

A *variant* is a distinct ordered sequence of activities. We group cases by
their variant, rank by frequency, and report each variant's share of total
volume and average throughput time. The activity sequence is returned so the
frontend can highlight the matching path in the process graph (Story 2.3).
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from sqlalchemy.orm import Session

from app.schemas.analysis import Variant, VariantReport, VariantRequest
from app.services.process_data import Trace, load_traces


def _throughput_seconds(trace: Trace) -> float:
    if len(trace) < 2:
        return 0.0
    return max((trace[-1][1] - trace[0][1]).total_seconds(), 0.0)


def analyze_variants(
    db: Session, log_id: str, params: VariantRequest
) -> VariantReport:
    traces = load_traces(db, log_id)
    total_cases = len(traces)

    sequences: dict[tuple[str, ...], list[float]] = defaultdict(list)
    for trace in traces.values():
        seq = tuple(act for act, _ts in trace)
        sequences[seq].append(_throughput_seconds(trace))

    ranked = sorted(
        sequences.items(), key=lambda kv: (-len(kv[1]), kv[0])
    )

    variants: list[Variant] = []
    rank = 0
    for seq, throughputs in ranked:
        case_count = len(throughputs)
        if case_count < params.min_frequency:
            continue
        rank += 1
        if params.top_n is not None and rank > params.top_n:
            break
        variants.append(
            Variant(
                rank=rank,
                sequence=list(seq),
                case_count=case_count,
                percentage=round(100.0 * case_count / total_cases, 2)
                if total_cases
                else 0.0,
                avg_throughput_seconds=round(mean(throughputs), 2),
            )
        )

    return VariantReport(
        log_id=log_id,
        case_count=total_cases,
        variant_count=len(sequences),
        variants=variants,
    )
