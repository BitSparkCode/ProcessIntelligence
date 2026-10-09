"""Shared helpers to load a stored event log into analysis-friendly shapes.

Discovery, variant, performance, case-inspection and simulation all start from
the same ordered per-case event stream, so the loading logic lives here to
avoid duplication. Sprint 6 added resource names on trace events plus the
Disco-style ``LogFilter`` applied before analysis.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity, Case, Event, Resource
from app.schemas.filters import LogFilter


@dataclass(frozen=True)
class TraceEvent:
    activity: str
    timestamp: datetime
    resource: str | None = None


# A trace is an ordered list of TraceEvents for one case.
Trace = list[TraceEvent]


def load_traces(
    db: Session, log_id: str, filters: LogFilter | None = None
) -> dict[str, Trace]:
    """Return {case_key: ordered TraceEvents} for a log, optionally filtered."""
    stmt = (
        select(Case.case_key, Activity.name, Event.timestamp, Resource.name)
        .join(Event, Event.case_id == Case.id)
        .join(Activity, Event.activity_id == Activity.id)
        .outerjoin(Resource, Event.resource_id == Resource.id)
        .where(Event.log_id == log_id)
        .order_by(Case.case_key, Event.timestamp)
    )
    by_case: dict[str, Trace] = defaultdict(list)
    for case_key, act_name, ts, res_name in db.execute(stmt):
        by_case[case_key].append(TraceEvent(act_name, ts, res_name))
    traces = dict(by_case)
    if filters is not None:
        traces = apply_filters(traces, filters)
    return traces


def _align(dt: datetime, reference: datetime) -> datetime:
    """Re-express ``dt`` with the same tz-awareness as ``reference``."""
    if (dt.tzinfo is None) == (reference.tzinfo is None):
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(tzinfo=None)


def apply_filters(traces: Mapping[str, Trace], flt: LogFilter) -> dict[str, Trace]:
    """Apply a LogFilter to loaded traces. May drop events and whole cases."""
    out: dict[str, Trace] = {}
    include = set(flt.include_activities)
    exclude = set(flt.exclude_activities)
    resources = set(flt.resources)
    for case_key, trace in traces.items():
        if not trace:
            continue
        first_ts = trace[0].timestamp
        from_ts = _align(flt.from_ts, first_ts) if flt.from_ts else None
        to_ts = _align(flt.to_ts, first_ts) if flt.to_ts else None
        if from_ts is not None and first_ts < from_ts:
            continue
        if to_ts is not None and first_ts > to_ts:
            continue
        if flt.start_activities and trace[0].activity not in flt.start_activities:
            continue
        if flt.end_activities and trace[-1].activity not in flt.end_activities:
            continue

        events = [
            ev
            for ev in trace
            if (not include or ev.activity in include)
            and ev.activity not in exclude
            and (not resources or ev.resource in resources)
        ]
        if not events:
            continue

        if flt.min_duration_seconds is not None or flt.max_duration_seconds is not None:
            duration = max(
                (events[-1].timestamp - events[0].timestamp).total_seconds(), 0.0
            )
            if flt.min_duration_seconds is not None and duration < flt.min_duration_seconds:
                continue
            if flt.max_duration_seconds is not None and duration > flt.max_duration_seconds:
                continue

        out[case_key] = events
    return out


def load_dataframe(
    db: Session, log_id: str, filters: LogFilter | None = None
) -> pd.DataFrame:
    """Build a PM4Py-formatted event DataFrame for a log.

    Columns follow the PM4Py standard: ``case:concept:name``, ``concept:name``
    and ``time:timestamp``. Returns an empty frame (with the right columns) when
    the log has no events.
    """
    columns = ["case:concept:name", "concept:name", "time:timestamp"]
    rows: list[dict[str, object]] = []
    for case_key, trace in load_traces(db, log_id, filters).items():
        for ev in trace:
            rows.append(
                {
                    "case:concept:name": case_key,
                    "concept:name": ev.activity,
                    "time:timestamp": ev.timestamp,
                }
            )
    if not rows:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(rows, columns=columns)
    df["time:timestamp"] = pd.to_datetime(df["time:timestamp"], utc=True)
    return df
