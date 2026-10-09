"""Heuristic Miner process discovery (Story 2.1).

Builds a directly-follows graph (DFG) from a stored event log and computes the
Heuristic Miner dependency measure per edge, plus activity/edge frequencies and
average transition durations. Thresholds prune noise. The output is a plain
graph the n8n-style frontend canvas (Story 2.3) renders directly.

Sprint 6: traces load through the shared, filter-aware loader so the discovery
view honors the same LogFilter as every other analysis.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.schemas.discovery import (
    ActivityNode,
    DiscoveryRequest,
    ProcessEdge,
    ProcessGraph,
)
from app.services.process_data import load_traces


def discover_heuristic_net(
    db: Session, log_id: str, params: DiscoveryRequest
) -> ProcessGraph:
    traces = list(load_traces(db, log_id, params.filters).values())

    activity_freq: dict[str, int] = defaultdict(int)
    df_count: dict[tuple[str, str], int] = defaultdict(int)
    df_duration: dict[tuple[str, str], float] = defaultdict(float)
    start_freq: dict[str, int] = defaultdict(int)
    end_freq: dict[str, int] = defaultdict(int)

    for trace in traces:
        if not trace:
            continue
        start_freq[trace[0].activity] += 1
        end_freq[trace[-1].activity] += 1
        for ev in trace:
            activity_freq[ev.activity] += 1
        for a, b in zip(trace, trace[1:], strict=False):
            pair = (a.activity, b.activity)
            df_count[pair] += 1
            df_duration[pair] += max(
                (b.timestamp - a.timestamp).total_seconds(), 0.0
            )

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
    total_w = sum(e.frequency for e in out)
    if total_w == 0:
        return None
    return round(
        sum(e.avg_duration_seconds * e.frequency for e in out) / total_w, 2
    )
