"""Case inspector, log replay and overview stats (Sprint 6).

Disco-style case browser: a sortable case list, a per-case event timeline, a
compact replay payload that drives the animated process map, and the summary
numbers behind the Overview tab.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from statistics import mean, median

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.schemas.analysis import (
    CaseDetailReport,
    CaseEventOut,
    CaseEventsRequest,
    CaseListReport,
    CaseListRequest,
    CaseSummary,
    NamedCount,
    OverviewReport,
    OverviewRequest,
    ReplayCase,
    ReplayReport,
    ReplayRequest,
    TimeBucket,
)
from app.services.process_data import Trace, load_traces


def _duration(trace: Trace) -> float:
    if len(trace) < 2:
        return 0.0
    return max(
        (trace[-1].timestamp - trace[0].timestamp).total_seconds(), 0.0
    )


def list_cases(
    db: Session, log_id: str, params: CaseListRequest
) -> CaseListReport:
    traces = load_traces(db, log_id, params.filters)

    rows: list[CaseSummary] = []
    for case_key, trace in traces.items():
        if params.search and params.search.lower() not in case_key.lower():
            continue
        rows.append(
            CaseSummary(
                case_key=case_key,
                start=trace[0].timestamp,
                end=trace[-1].timestamp,
                duration_seconds=round(_duration(trace), 2),
                event_count=len(trace),
                variant=[ev.activity for ev in trace],
            )
        )

    key_fns = {
        "start": lambda c: c.start,
        "duration": lambda c: c.duration_seconds,
        "events": lambda c: c.event_count,
    }
    key_fn = key_fns.get(params.sort, key_fns["start"])
    rows.sort(key=key_fn, reverse=params.descending)

    total = len(rows)
    start = (params.page - 1) * params.page_size
    page_rows = rows[start : start + params.page_size]
    return CaseListReport(
        log_id=log_id,
        total_cases=total,
        page=params.page,
        page_size=params.page_size,
        cases=page_rows,
    )


def case_detail(
    db: Session, log_id: str, params: CaseEventsRequest
) -> CaseDetailReport:
    traces = load_traces(db, log_id)
    trace = traces.get(params.case_key)
    if trace is None:
        raise HTTPException(status_code=404, detail="Case not found")

    events: list[CaseEventOut] = []
    for i, ev in enumerate(trace):
        nxt = trace[i + 1] if i + 1 < len(trace) else None
        events.append(
            CaseEventOut(
                activity=ev.activity,
                timestamp=ev.timestamp,
                resource=ev.resource,
                gap_to_next_seconds=(
                    round((nxt.timestamp - ev.timestamp).total_seconds(), 2)
                    if nxt
                    else None
                ),
            )
        )
    return CaseDetailReport(
        log_id=log_id,
        case_key=params.case_key,
        duration_seconds=round(_duration(trace), 2),
        events=events,
    )


def replay_data(
    db: Session, log_id: str, params: ReplayRequest
) -> ReplayReport:
    """Compact timeline used by the animated process-map replay."""
    traces = load_traces(db, log_id, params.filters)
    if not traces:
        return ReplayReport(
            log_id=log_id, case_count=0, horizon_seconds=0.0, cases=[]
        )

    t0 = min(ev.timestamp for trace in traces.values() for ev in trace)
    t_end = max(ev.timestamp for trace in traces.values() for ev in trace)

    # Newest cases first so the replay favours recent behaviour when capped.
    ordered = sorted(
        traces.items(), key=lambda kv: kv[1][0].timestamp, reverse=True
    )[: params.max_cases]

    cases = [
        ReplayCase(
            case_key=case_key,
            events=[
                [ev.activity, round((ev.timestamp - t0).total_seconds(), 2)]
                for ev in trace
            ],
        )
        for case_key, trace in ordered
    ]
    return ReplayReport(
        log_id=log_id,
        case_count=len(cases),
        horizon_seconds=round((t_end - t0).total_seconds(), 2),
        cases=cases,
    )


def overview(db: Session, log_id: str, params: OverviewRequest) -> OverviewReport:
    traces = load_traces(db, log_id, params.filters)

    activity_freq: Counter[str] = Counter()
    resource_freq: Counter[str] = Counter()
    variant_freq: Counter[tuple[str, ...]] = Counter()
    throughputs: list[float] = []
    first_ts = None
    last_ts = None

    for trace in traces.values():
        if not trace:
            continue
        variant_freq[tuple(ev.activity for ev in trace)] += 1
        throughputs.append(_duration(trace))
        for ev in trace:
            activity_freq[ev.activity] += 1
            if ev.resource:
                resource_freq[ev.resource] += 1
            if first_ts is None or ev.timestamp < first_ts:
                first_ts = ev.timestamp
            if last_ts is None or ev.timestamp > last_ts:
                last_ts = ev.timestamp

    cases_over_time: list[TimeBucket] = []
    if first_ts is not None and last_ts is not None:
        span = max((last_ts - first_ts).total_seconds(), 1.0)
        width = span / params.buckets
        counts = [0] * params.buckets
        for trace in traces.values():
            if not trace:
                continue
            idx = min(
                int((trace[0].timestamp - first_ts).total_seconds() / width),
                params.buckets - 1,
            )
            counts[idx] += 1
        cases_over_time = [
            TimeBucket(
                start=first_ts + timedelta(seconds=i * width), count=counts[i]
            )
            for i in range(params.buckets)
        ]

    return OverviewReport(
        log_id=log_id,
        case_count=len(traces),
        event_count=sum(len(t) for t in traces.values()),
        activity_count=len(activity_freq),
        resource_count=len(resource_freq),
        variant_count=len(variant_freq),
        first_event=first_ts,
        last_event=last_ts,
        mean_throughput_seconds=round(mean(throughputs), 2) if throughputs else 0.0,
        median_throughput_seconds=(
            round(median(throughputs), 2) if throughputs else 0.0
        ),
        cases_over_time=cases_over_time,
        top_activities=[
            NamedCount(name=n, count=c) for n, c in activity_freq.most_common(10)
        ],
        top_resources=[
            NamedCount(name=n, count=c) for n, c in resource_freq.most_common(10)
        ],
    )
