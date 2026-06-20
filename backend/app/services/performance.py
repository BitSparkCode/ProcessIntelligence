"""Throughput-time dashboard (Story 3.1).

Aggregates timing metrics over a stored event log: case throughput KPIs
(avg/median/min/max), per-activity waiting times, transition waiting times, and
a throughput-time distribution histogram. An optional time window keeps only
cases that start within ``window_days`` of the most recent event.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from statistics import mean, median

from sqlalchemy.orm import Session

from app.schemas.analysis import (
    ActivityStat,
    HistogramBin,
    PerformanceReport,
    PerformanceRequest,
    TransitionStat,
)
from app.services.process_data import Trace, load_traces


def _throughput_seconds(trace: Trace) -> float:
    if len(trace) < 2:
        return 0.0
    return max((trace[-1][1] - trace[0][1]).total_seconds(), 0.0)


def _filter_window(traces: list[Trace], window_days: int | None) -> list[Trace]:
    if window_days is None or not traces:
        return traces
    latest = max(t[-1][1] for t in traces if t)
    cutoff = latest - timedelta(days=window_days)
    return [t for t in traces if t and t[0][1] >= cutoff]


def _histogram(values: list[float], bins: int) -> list[HistogramBin]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high == low:
        return [HistogramBin(lower_seconds=low, upper_seconds=high, count=len(values))]
    width = (high - low) / bins
    counts = [0] * bins
    for v in values:
        idx = min(int((v - low) / width), bins - 1)
        counts[idx] += 1
    return [
        HistogramBin(
            lower_seconds=round(low + i * width, 2),
            upper_seconds=round(low + (i + 1) * width, 2),
            count=counts[i],
        )
        for i in range(bins)
    ]


def compute_performance(
    db: Session, log_id: str, params: PerformanceRequest
) -> PerformanceReport:
    all_traces = list(load_traces(db, log_id).values())
    traces = _filter_window(all_traces, params.window_days)

    throughputs = [_throughput_seconds(t) for t in traces if t]
    event_count = sum(len(t) for t in traces)

    activity_freq: dict[str, int] = defaultdict(int)
    out_count: dict[str, int] = defaultdict(int)
    out_duration: dict[str, float] = defaultdict(float)
    tr_count: dict[tuple[str, str], int] = defaultdict(int)
    tr_duration: dict[tuple[str, str], float] = defaultdict(float)

    for trace in traces:
        for act, _ts in trace:
            activity_freq[act] += 1
        for (a_act, a_ts), (b_act, b_ts) in zip(trace, trace[1:], strict=False):
            gap = max((b_ts - a_ts).total_seconds(), 0.0)
            out_count[a_act] += 1
            out_duration[a_act] += gap
            tr_count[(a_act, b_act)] += 1
            tr_duration[(a_act, b_act)] += gap

    activity_stats = [
        ActivityStat(
            activity=act,
            frequency=freq,
            avg_duration_to_next_seconds=(
                round(out_duration[act] / out_count[act], 2)
                if out_count.get(act)
                else None
            ),
        )
        for act, freq in sorted(activity_freq.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    transition_stats = [
        TransitionStat(
            source=a,
            target=b,
            frequency=count,
            avg_waiting_seconds=round(tr_duration[(a, b)] / count, 2),
        )
        for (a, b), count in sorted(tr_count.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    return PerformanceReport(
        log_id=log_id,
        case_count=len(traces),
        event_count=event_count,
        avg_throughput_seconds=round(mean(throughputs), 2) if throughputs else 0.0,
        median_throughput_seconds=round(median(throughputs), 2) if throughputs else 0.0,
        min_throughput_seconds=round(min(throughputs), 2) if throughputs else 0.0,
        max_throughput_seconds=round(max(throughputs), 2) if throughputs else 0.0,
        activity_stats=activity_stats,
        transition_stats=transition_stats,
        histogram=_histogram(throughputs, params.histogram_bins),
        window_days=params.window_days,
    )
