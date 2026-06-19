"""Heuristic Miner process discovery (Story 2.1).

Builds a directly-follows graph (DFG) from a stored event log and computes the
Heuristic Miner dependency measure per edge, plus activity/edge frequencies and
average transition durations. Thresholds prune noise. The output is a plain
graph the n8n-style frontend canvas (Story 2.3) renders directly.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity, Event
from app.schemas.discovery import (
    ActivityNode,
    DiscoveryRequest,
    ProcessEdge,
    ProcessGraph,
)


def discover_heuristic_net(
    db: Session, log_id: str, params: DiscoveryRequest
) -> ProcessGraph:
    traces = _load_traces(db, log_id)

    activity_freq: dict[str, int] = defaultdict(int)
    df_count: dict[tuple[str, str], int] = defaultdict(int)
    df_duration: dict[tuple[str, str], float] = defaultdict(float)
    start_freq: dict[str, int] = defaultdict(int)
    end_freq: dict[str, int] = defaultdict(int)

    for trace in traces:
        if not trace:
            continue
        start_freq[trace[0][0]] += 1
        end_freq[trace[-1][0]] += 1
        for (act, _ts) in trace:
            activity_freq[act] += 1
        for (a_act, a_ts), (b_act, b_ts) in zip(trace, trace[1:], strict=False):
            pair = (a_act, b_act)
            df_count[pair] += 1
            df_duration[pair] += max((b_ts - a_ts), 0.0)

    edges = _build_edges(df_count, df_duration, params)

    # Only keep activities that are connected (or are start/end) after pruning.
    kept_acts = set(activity_freq)
    nodes = [
        ActivityNode(
            id=act,
            label=act,
            frequency=activity_freq[act],
            is_start=act in start_freq,
            is_end=act in end_freq,
            avg_duration_seconds=_avg_outgoing_duration(act, edges),
        )
        for act in sorted(kept_acts)
    ]

    return ProcessGraph(
        log_id=log_id,
        nodes=nodes,
        edges=edges,
        case_count=len(traces),
        event_count=sum(activity_freq.values()),
        start_activities=sorted(start_freq),
        end_activities=sorted(end_freq),
        dependency_threshold=params.dependency_threshold,
        frequency_threshold=params.frequency_threshold,
    )


def _build_edges(
    df_count: dict[tuple[str, str], int],
    df_duration: dict[tuple[str, str], float],
    params: DiscoveryRequest,
) -> list[ProcessEdge]:
    edges: list[ProcessEdge] = []
    for (a, b), count in df_count.items():
        if count < params.frequency_threshold:
            continue
        reverse = df_count.get((b, a), 0)
        if a == b:
            # self-loop dependency measure
            dependency = count / (count + 1)
        else:
            dependency = (count - reverse) / (count + reverse + 1)
        if dependency < params.dependency_threshold:
            continue
        edges.append(
            ProcessEdge(
                source=a,
                target=b,
                frequency=count,
                dependency=round(dependency, 4),
                avg_duration_seconds=round(df_duration[(a, b)] / count, 2),
            )
        )
    return edges


def _avg_outgoing_duration(act: str, edges: list[ProcessEdge]) -> float | None:
    out = [e for e in edges if e.source == act]
    if not out:
        return None
    total_w = sum(e.frequency for e in out)
    if total_w == 0:
        return None
    return round(
        sum(e.avg_duration_seconds * e.frequency for e in out) / total_w, 2
    )


def _load_traces(db: Session, log_id: str) -> list[list[tuple[str, float]]]:
    """Return per-case ordered lists of (activity_name, epoch_seconds)."""
    stmt = (
        select(Event.case_id, Activity.name, Event.timestamp)
        .join(Activity, Event.activity_id == Activity.id)
        .where(Event.log_id == log_id)
        .order_by(Event.case_id, Event.timestamp)
    )
    by_case: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for case_id, act_name, ts in db.execute(stmt):
        by_case[case_id].append((act_name, ts.timestamp()))
    return list(by_case.values())
