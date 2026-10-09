"""Process simulation (Sprint 6).

A small discrete-event simulation over the directly-follows model learned from
the log. Cases arrive as a Poisson stream, flow through activities sampled from
the observed transition probabilities, and wait when an activity's resource
pool is exhausted. Service times are drawn from the empirical per-activity
durations (event -> next event gap) times a what-if multiplier. The result is a
case-duration distribution plus per-activity queue/utilization stats, compared
against the observed baseline.

Runs are deterministic for a fixed ``seed``.
"""

from __future__ import annotations

import heapq
import math
import random
from collections import Counter, defaultdict, deque
from statistics import mean, median
from typing import cast

from sqlalchemy.orm import Session

from app.schemas.analysis import (
    ActivitySimStat,
    DurationStats,
    SimulationReport,
    SimulationRequest,
)
from app.services.performance import _histogram
from app.services.process_data import Trace, load_traces

_END = "__end__"


def _percentile(values: list[float], pct: float) -> float:
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


def _duration_stats(values: list[float]) -> DurationStats:
    return DurationStats(
        mean_seconds=round(mean(values), 2) if values else 0.0,
        median_seconds=round(median(values), 2) if values else 0.0,
        p90_seconds=round(_percentile(values, 90), 2),
        min_seconds=round(min(values), 2) if values else 0.0,
        max_seconds=round(max(values), 2) if values else 0.0,
    )


def _pick(rng: random.Random, dist: Counter[str]) -> str:
    total = sum(dist.values())
    mark = rng.uniform(0, total)
    upto = 0.0
    for key, weight in dist.items():
        upto += weight
        if mark <= upto:
            return key
    return next(iter(dist))


def _build_model(
    traces: list[Trace],
) -> tuple[Counter[str], dict[str, Counter[str]], dict[str, list[float]]]:
    """Start distribution, transition counts and per-activity durations."""
    starts: Counter[str] = Counter()
    transitions: dict[str, Counter[str]] = defaultdict(Counter)
    durations: dict[str, list[float]] = defaultdict(list)

    for trace in traces:
        if not trace:
            continue
        starts[trace[0].activity] += 1
        for i, ev in enumerate(trace):
            nxt = trace[i + 1] if i + 1 < len(trace) else None
            if nxt is None:
                transitions[ev.activity][_END] += 1
            else:
                transitions[ev.activity][nxt.activity] += 1
                durations[ev.activity].append(
                    max((nxt.timestamp - ev.timestamp).total_seconds(), 0.0)
                )
    return starts, transitions, durations


def simulate(
    db: Session, log_id: str, params: SimulationRequest
) -> SimulationReport:
    traces = list(load_traces(db, log_id, params.filters).values())
    starts, transitions, durations = _build_model(traces)
    if not starts:
        return SimulationReport(
            log_id=log_id,
            simulated_cases=0,
            horizon_seconds=0.0,
            arrival_rate_per_day=0.0,
            baseline=None,
            simulated=_duration_stats([]),
            histogram=[],
            activity_stats=[],
        )

    rng = random.Random(params.seed)

    observed_throughputs = [
        max((t[-1].timestamp - t[0].timestamp).total_seconds(), 0.0)
        for t in traces
        if t
    ]
    observed_activity_gap = {
        act: mean(samples) for act, samples in durations.items() if samples
    }

    # Arrival rate: user value, else estimated from the observed window.
    if params.arrival_rate_per_day:
        rate_per_day = params.arrival_rate_per_day
    else:
        first_ts = min(ev.timestamp for t in traces for ev in t)
        last_ts = max(ev.timestamp for t in traces for ev in t)
        span_days = max((last_ts - first_ts).total_seconds() / 86400.0, 1e-6)
        rate_per_day = len(traces) / span_days
    rate_per_day *= params.arrival_rate_multiplier
    interarrival_mean = 86400.0 / rate_per_day

    def servers_for(activity: str) -> int | None:
        """Parallel capacity; None means unlimited."""
        if activity in params.resource_pools:
            return params.resource_pools[activity]
        return params.default_servers

    def service_time(activity: str) -> float:
        samples = durations.get(activity)
        base = rng.choice(samples) if samples else 0.0
        return (
            base
            * params.duration_multipliers.get(activity, 1.0)
            * params.global_duration_multiplier
        )

    # Event queue entries: (time, seq, kind, payload)
    event_queue: list[tuple[float, int, str, object]] = []
    seq = 0

    def push(t: float, kind: str, payload: object) -> None:
        nonlocal seq
        heapq.heappush(event_queue, (t, seq, kind, payload))
        seq += 1

    free: dict[str, int] = {}  # activity -> free servers (capped pools only)
    waiting: dict[str, deque[tuple[int, float]]] = defaultdict(deque)
    waits: dict[str, list[float]] = defaultdict(list)
    service_times: dict[str, list[float]] = defaultdict(list)
    busy_time: dict[str, float] = defaultdict(float)
    executions: Counter[str] = Counter()
    birth: dict[int, float] = {}
    case_durations: list[float] = []

    def try_start(now: float, case_idx: int, activity: str) -> None:
        cap = servers_for(activity)
        if cap is not None:
            free.setdefault(activity, cap)
            if free[activity] <= 0:
                waiting[activity].append((case_idx, now))
                return
            free[activity] -= 1
        _run(now, case_idx, activity)

    def _run(now: float, case_idx: int, activity: str) -> None:
        service = service_time(activity)
        service_times[activity].append(service)
        executions[activity] += 1
        push(now + service, "complete", (case_idx, activity, now))

    # Schedule arrivals as a cumulative Poisson stream.
    t = 0.0
    for case_idx in range(params.cases):
        t += rng.expovariate(1.0 / interarrival_mean)
        birth[case_idx] = t
        push(t, "arrive", case_idx)

    sim_end = 0.0
    while event_queue:
        now, _s, kind, payload = heapq.heappop(event_queue)
        sim_end = max(sim_end, now)

        if kind == "arrive":
            try_start(now, cast(int, payload), _pick(rng, starts))
            continue

        # completion: free the server, then route the case onward
        case_idx, activity, started_at = cast("tuple[int, str, float]", payload)
        busy_time[activity] += now - started_at

        cap = servers_for(activity)
        if cap is not None:
            free[activity] += 1
            while free[activity] > 0 and waiting[activity]:
                queued_case, queued_since = waiting[activity].popleft()
                waits[activity].append(now - queued_since)
                free[activity] -= 1
                _run(now, queued_case, activity)

        nxt = _pick(rng, transitions[activity])
        if nxt == _END:
            case_durations.append(now - birth[case_idx])
        else:
            try_start(now, case_idx, nxt)

    horizon = sim_end if sim_end > 0 else 1.0
    activity_stats = []
    for act in sorted(executions, key=lambda a: -executions[a]):
        cap = servers_for(act)
        activity_stats.append(
            ActivitySimStat(
                activity=act,
                executions=executions[act],
                servers=cap,
                mean_service_seconds=round(mean(service_times[act]), 2),
                mean_wait_seconds=(
                    round(mean(waits[act]), 2) if waits[act] else 0.0
                ),
                max_wait_seconds=(
                    round(max(waits[act]), 2) if waits[act] else 0.0
                ),
                utilization=(
                    round(min(busy_time[act] / (cap * horizon), 1.0), 3)
                    if cap
                    else None
                ),
                observed_mean_seconds=(
                    round(observed_activity_gap[act], 2)
                    if act in observed_activity_gap
                    else None
                ),
            )
        )

    return SimulationReport(
        log_id=log_id,
        simulated_cases=len(case_durations),
        horizon_seconds=round(horizon, 2),
        arrival_rate_per_day=round(rate_per_day, 4),
        baseline=_duration_stats(observed_throughputs),
        simulated=_duration_stats(case_durations),
        histogram=_histogram(case_durations, params.histogram_bins),
        activity_stats=activity_stats,
    )
