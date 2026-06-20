"""Shared helpers to load a stored event log into analysis-friendly shapes.

Discovery, variant and performance analysis all start from the same ordered
per-case event stream, so the loading logic lives here to avoid duplication.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity, Case, Event

# A trace is an ordered list of (activity_name, timestamp) for one case.
Trace = list[tuple[str, datetime]]


def load_traces(db: Session, log_id: str) -> dict[str, Trace]:
    """Return {case_key: ordered [(activity, timestamp)]} for a log."""
    stmt = (
        select(Case.case_key, Activity.name, Event.timestamp)
        .join(Event, Event.case_id == Case.id)
        .join(Activity, Event.activity_id == Activity.id)
        .where(Event.log_id == log_id)
        .order_by(Case.case_key, Event.timestamp)
    )
    by_case: dict[str, Trace] = defaultdict(list)
    for case_key, act_name, ts in db.execute(stmt):
        by_case[case_key].append((act_name, ts))
    return dict(by_case)


def load_dataframe(db: Session, log_id: str) -> pd.DataFrame:
    """Build a PM4Py-formatted event DataFrame for a log.

    Columns follow the PM4Py standard: ``case:concept:name``, ``concept:name``
    and ``time:timestamp``. Returns an empty frame (with the right columns) when
    the log has no events.
    """
    columns = ["case:concept:name", "concept:name", "time:timestamp"]
    rows: list[dict[str, object]] = []
    for case_key, trace in load_traces(db, log_id).items():
        for act, ts in trace:
            rows.append(
                {
                    "case:concept:name": case_key,
                    "concept:name": act,
                    "time:timestamp": ts,
                }
            )
    if not rows:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(rows, columns=columns)
    df["time:timestamp"] = pd.to_datetime(df["time:timestamp"], utc=True)
    return df
