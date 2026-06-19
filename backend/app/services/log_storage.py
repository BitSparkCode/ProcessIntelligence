"""Persist normalized events into the internal event-log schema.

Events are written in batches so that very large logs (hundreds of MB / millions of
events) can be imported with bounded memory.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.models import Activity, Case, Event, EventLog, Resource
from app.schemas.event_log import ImportResult
from app.services.csv_import import NormalizedEvent

BATCH_SIZE = 5000


def _uuid() -> str:
    return str(uuid.uuid4())


def persist_log(
    db: Session,
    *,
    name: str,
    source: str,
    events: Iterable[NormalizedEvent],
) -> ImportResult:
    log = EventLog(id=_uuid(), name=name, source=source, row_count=0, case_count=0)
    db.add(log)
    db.flush()

    activity_ids: dict[str, str] = {}
    resource_ids: dict[str, str] = {}
    case_ids: dict[str, str] = {}

    pending_activities: list[dict] = []
    pending_resources: list[dict] = []
    pending_cases: list[dict] = []
    pending_events: list[dict] = []

    row_count = 0

    def flush() -> None:
        if pending_activities:
            db.execute(insert(Activity), pending_activities)
            pending_activities.clear()
        if pending_resources:
            db.execute(insert(Resource), pending_resources)
            pending_resources.clear()
        if pending_cases:
            db.execute(insert(Case), pending_cases)
            pending_cases.clear()
        if pending_events:
            db.execute(insert(Event), pending_events)
            pending_events.clear()

    for ev in events:
        activity_id = activity_ids.get(ev.activity)
        if activity_id is None:
            activity_id = _uuid()
            activity_ids[ev.activity] = activity_id
            pending_activities.append({"id": activity_id, "log_id": log.id, "name": ev.activity})

        resource_id: str | None = None
        if ev.resource:
            resource_id = resource_ids.get(ev.resource)
            if resource_id is None:
                resource_id = _uuid()
                resource_ids[ev.resource] = resource_id
                pending_resources.append(
                    {"id": resource_id, "log_id": log.id, "name": ev.resource}
                )

        case_id = case_ids.get(ev.case_key)
        if case_id is None:
            case_id = _uuid()
            case_ids[ev.case_key] = case_id
            pending_cases.append({"id": case_id, "log_id": log.id, "case_key": ev.case_key})

        pending_events.append(
            {
                "id": _uuid(),
                "log_id": log.id,
                "case_id": case_id,
                "activity_id": activity_id,
                "resource_id": resource_id,
                "timestamp": ev.timestamp,
                "lifecycle": ev.lifecycle,
                "cost": ev.cost,
            }
        )
        row_count += 1

        if len(pending_events) >= BATCH_SIZE:
            flush()

    flush()

    log.row_count = row_count
    log.case_count = len(case_ids)
    db.add(log)
    db.commit()

    return ImportResult(
        log_id=log.id,
        name=log.name,
        row_count=row_count,
        case_count=len(case_ids),
        activity_count=len(activity_ids),
    )


def delete_log(db: Session, log_id: str) -> bool:
    log = db.get(EventLog, log_id)
    if log is None:
        return False
    db.delete(log)
    db.commit()
    return True


__all__ = ["persist_log", "delete_log"]
