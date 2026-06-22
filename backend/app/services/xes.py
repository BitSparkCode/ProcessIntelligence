"""XES (IEEE 1849-2016) import & export (Story 1.2).

Wraps PM4Py's XES reader/writer so event logs can be exchanged with PM4Py, ProM,
Apromore and academic datasets (e.g. the BPI Challenge logs). Import maps the
standard XES attributes onto the internal :class:`NormalizedEvent`; export
projects a stored log back to a schema-valid ``.xes`` document.
"""

from __future__ import annotations

import math
import os
import tempfile

import pandas as pd
import pm4py
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity, Case, Event, Resource
from app.services.csv_import import NormalizedEvent

# Standard XES attribute keys (PM4Py column names).
_CASE = "case:concept:name"
_ACTIVITY = "concept:name"
_TIMESTAMP = "time:timestamp"
_RESOURCE = "org:resource"
_LIFECYCLE = "lifecycle:transition"
_COST = "cost:total"


class XesError(Exception):
    """Raised when an XES file cannot be read or contains no usable events."""


def _clean(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text or None


def import_xes(path: str) -> list[NormalizedEvent]:
    """Parse a ``.xes`` / ``.xes.gz`` file into normalized events.

    Rows missing a case id, activity or timestamp are skipped (XES guarantees
    these, but real-world files are messy).
    """
    try:
        df = pm4py.read_xes(path)
    except Exception as exc:  # noqa: BLE001 - surface any parser failure uniformly
        raise XesError(f"Could not read XES file: {exc}") from exc

    if not isinstance(df, pd.DataFrame):
        df = pm4py.convert_to_dataframe(df)
    if df.empty or _CASE not in df.columns or _ACTIVITY not in df.columns:
        raise XesError("XES file contains no events with the required attributes")

    events: list[NormalizedEvent] = []
    for row in df.to_dict("records"):
        case_key = _clean(row.get(_CASE))
        activity = _clean(row.get(_ACTIVITY))
        ts = row.get(_TIMESTAMP)
        if not case_key or not activity or ts is None:
            continue
        timestamp = pd.to_datetime(ts, utc=True).to_pydatetime()
        cost_raw = row.get(_COST)
        cost = None
        if cost_raw is not None and not (
            isinstance(cost_raw, float) and math.isnan(cost_raw)
        ):
            try:
                cost = float(cost_raw)
            except (TypeError, ValueError):
                cost = None
        events.append(
            NormalizedEvent(
                case_key=case_key,
                activity=activity,
                timestamp=timestamp,
                resource=_clean(row.get(_RESOURCE)),
                lifecycle=_clean(row.get(_LIFECYCLE)),
                cost=cost,
            )
        )
    if not events:
        raise XesError("XES file contains no events with the required attributes")
    return events


def _export_dataframe(db: Session, log_id: str) -> pd.DataFrame:
    """Load a stored log as a PM4Py dataframe including resource/lifecycle/cost."""
    stmt = (
        select(
            Case.case_key,
            Activity.name,
            Event.timestamp,
            Resource.name,
            Event.lifecycle,
            Event.cost,
        )
        .join(Event, Event.case_id == Case.id)
        .join(Activity, Event.activity_id == Activity.id)
        .join(Resource, Event.resource_id == Resource.id, isouter=True)
        .where(Event.log_id == log_id)
        .order_by(Case.case_key, Event.timestamp)
    )
    rows: list[dict[str, object]] = []
    for case_key, activity, ts, resource, lifecycle, cost in db.execute(stmt):
        record: dict[str, object] = {
            _CASE: case_key,
            _ACTIVITY: activity,
            _TIMESTAMP: ts,
        }
        if resource is not None:
            record[_RESOURCE] = resource
        if lifecycle is not None:
            record[_LIFECYCLE] = lifecycle
        if cost is not None:
            record[_COST] = cost
        rows.append(record)
    columns = [_CASE, _ACTIVITY, _TIMESTAMP]
    df = pd.DataFrame(rows, columns=columns if not rows else None)
    if not df.empty:
        df[_TIMESTAMP] = pd.to_datetime(df[_TIMESTAMP], utc=True)
    return df


def export_xes(db: Session, log_id: str) -> str:
    """Serialize a stored event log to a schema-valid XES XML string."""
    df = _export_dataframe(db, log_id)
    fd, path = tempfile.mkstemp(suffix=".xes")
    os.close(fd)
    try:
        if df.empty:
            # PM4Py rejects empty frames; emit a minimal valid empty log.
            return _empty_xes()
        df = pm4py.format_dataframe(
            df,
            case_id=_CASE,
            activity_key=_ACTIVITY,
            timestamp_key=_TIMESTAMP,
        )
        pm4py.write_xes(df, path, case_id_key=_CASE)
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    finally:
        if os.path.exists(path):
            os.remove(path)


def _empty_xes() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<log xes.version="1.0" xes.features="nested-attributes" '
        'xmlns="http://www.xes-standard.org/">\n'
        '\t<extension name="Concept" prefix="concept" '
        'uri="http://www.xes-standard.org/concept.xesext"/>\n'
        "</log>\n"
    )
