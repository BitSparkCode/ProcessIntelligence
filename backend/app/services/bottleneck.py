"""Bottleneck detection (Story 3.2).

Flags transitions (edges) and activities (nodes) whose mean waiting time is
unusually high relative to the rest of the process. "Unusually high" is defined
by a configurable percentile (default 90th) computed over the population of all
individual waiting times, so the cut-off adapts to each log instead of using a
hard-coded duration. Returns the full list of flagged steps plus a Top-N
plain-text summary that the API can export.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta

from sqlalchemy.orm import Session

from app.schemas.analysis import Bottleneck, BottleneckReport, BottleneckRequest
from app.services.process_data import Trace, load_traces


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (same method as numpy's default)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[int(rank)]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _filter_window(traces: list[Trace], window_days: int | None) -> list[Trace]:
    if window_days is None or not traces:
        return traces
    latest = max(t[-1][1] for t in traces if t)
    cutoff = latest - timedelta(days=window_days)
    return [t for t in traces if t and t[0][1] >= cutoff]


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def detect_bottlenecks(
    db: Session, log_id: str, params: BottleneckRequest
) -> BottleneckReport:
    all_traces = list(load_traces(db, log_id).values())
    traces = _filter_window(all_traces, params.window_days)

    # Per-occurrence waiting times, grouped per transition and per activity.
    tr_times: dict[tuple[str, str], list[float]] = defaultdict(list)
    act_times: dict[str, list[float]] = defaultdict(list)
    all_waits: list[float] = []

    for trace in traces:
        for (a_act, a_ts), (b_act, b_ts) in zip(trace, trace[1:], strict=False):
            gap = max((b_ts - a_ts).total_seconds(), 0.0)
            tr_times[(a_act, b_act)].append(gap)
            act_times[a_act].append(gap)
            all_waits.append(gap)

    threshold = _percentile(all_waits, params.percentile)

    bottlenecks: list[Bottleneck] = []

    def severity(avg: float) -> float:
        return round(avg / threshold, 2) if threshold > 0 else 0.0

    for (src, tgt), times in tr_times.items():
        avg = sum(times) / len(times)
        if threshold > 0 and avg >= threshold:
            bottlenecks.append(
                Bottleneck(
                    kind="transition",
                    label=f"{src} \u2192 {tgt}",
                    source=src,
                    target=tgt,
                    avg_waiting_seconds=round(avg, 2),
                    max_waiting_seconds=round(max(times), 2),
                    frequency=len(times),
                    severity=severity(avg),
                )
            )

    for act, times in act_times.items():
        avg = sum(times) / len(times)
        if threshold > 0 and avg >= threshold:
            bottlenecks.append(
                Bottleneck(
                    kind="activity",
                    label=act,
                    source=act,
                    target=None,
                    avg_waiting_seconds=round(avg, 2),
                    max_waiting_seconds=round(max(times), 2),
                    frequency=len(times),
                    severity=severity(avg),
                )
            )

    bottlenecks.sort(key=lambda b: (-b.avg_waiting_seconds, b.label))
    top = bottlenecks[: params.top_n]

    summary = [
        f"Bottlenecks at the {params.percentile:g}th percentile "
        f"(threshold {_format_duration(threshold)} waiting time):"
    ]
    if top:
        for i, b in enumerate(top, start=1):
            kind = "transition" if b.kind == "transition" else "activity"
            summary.append(
                f"{i}. {b.label} ({kind}) — avg {_format_duration(b.avg_waiting_seconds)}, "
                f"max {_format_duration(b.max_waiting_seconds)}, "
                f"{b.severity:g}x threshold, {b.frequency} occurrence(s)"
            )
    else:
        summary.append("No bottlenecks detected at this threshold.")

    return BottleneckReport(
        log_id=log_id,
        percentile=params.percentile,
        threshold_seconds=round(threshold, 2),
        case_count=len(traces),
        bottleneck_count=len(bottlenecks),
        bottlenecks=bottlenecks,
        top=top,
        summary=summary,
        window_days=params.window_days,
    )
