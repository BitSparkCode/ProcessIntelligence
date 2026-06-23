from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import EventLog, User
from app.schemas.event_log import (
    ColumnMapping,
    CsvPreview,
    EventLogOut,
    ImportResult,
    MappingSuggestion,
)
from app.services import ai, csv_import, log_storage, xes
from app.services.xes import XesError

router = APIRouter(prefix="/api/logs", tags=["logs"])
settings = get_settings()

UPLOAD_CHUNK = 1024 * 1024


def _uploads_dir() -> str:
    os.makedirs(settings.uploads_dir, exist_ok=True)
    return settings.uploads_dir


def _upload_path(upload_id: str) -> str:
    # upload_id is a generated uuid; reject anything else to avoid path traversal.
    try:
        uuid.UUID(upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid upload id") from exc
    return os.path.join(_uploads_dir(), f"{upload_id}.csv")


async def _stream_to_disk(file: UploadFile, dest: str) -> None:
    written = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(UPLOAD_CHUNK):
            written += len(chunk)
            if written > settings.max_upload_bytes:
                out.close()
                os.remove(dest)
                raise HTTPException(
                    status_code=413, detail="File exceeds maximum upload size"
                )
            out.write(chunk)


def _get_owned_log(db: Session, log_id: str, user: User) -> EventLog:
    log = db.get(EventLog, log_id)
    if log is None or log.workspace_id != user.workspace_id:
        # Same 404 whether the log doesn't exist or belongs to another workspace,
        # so IDs can't be probed across tenants.
        raise HTTPException(status_code=404, detail="Log not found")
    return log


class UploadResponse(BaseModel):
    upload_id: str
    preview: CsvPreview
    suggestion: MappingSuggestion


class ImportRequest(BaseModel):
    upload_id: str
    name: str
    mapping: ColumnMapping


@router.post("/upload", response_model=UploadResponse)
async def upload_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")

    upload_id = str(uuid.uuid4())
    dest = _upload_path(upload_id)
    await _stream_to_disk(file, dest)

    preview = csv_import.preview_csv(dest)
    if not preview.columns:
        os.remove(dest)
        raise HTTPException(status_code=400, detail="CSV has no header row")

    # AI-assisted data linking (Story 6.1): propose a mapping. Falls back to
    # deterministic heuristics when AI is disabled.
    suggestion = ai.suggest_column_mapping(preview.columns, preview.rows)
    return UploadResponse(upload_id=upload_id, preview=preview, suggestion=suggestion)


@router.post("/import-xes", response_model=ImportResult)
async def import_xes_log(
    file: UploadFile = File(...),
    name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImportResult:
    fname = (file.filename or "").lower()
    if not (fname.endswith(".xes") or fname.endswith(".xes.gz")):
        raise HTTPException(
            status_code=400, detail="Only .xes and .xes.gz files are supported"
        )

    suffix = ".xes.gz" if fname.endswith(".xes.gz") else ".xes"
    dest = os.path.join(_uploads_dir(), f"{uuid.uuid4()}{suffix}")
    await _stream_to_disk(file, dest)
    try:
        events = xes.import_xes(dest)
    except XesError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        try:
            os.remove(dest)
        except OSError:
            pass

    return log_storage.persist_log(
        db,
        workspace_id=current_user.workspace_id,
        name=name or "Imported XES log",
        source="xes",
        events=events,
    )


@router.get("/{log_id}/export/xes")
def export_xes_log(
    log_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    log = _get_owned_log(db, log_id, current_user)
    xml = xes.export_xes(db, log_id)
    filename = f"{log.name or 'event-log'}.xes"
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", response_model=ImportResult)
def import_csv(
    req: ImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImportResult:
    path = _upload_path(req.upload_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Upload not found or expired")

    columns = csv_import.sniff_columns(path)
    errors = csv_import.validate_mapping(columns, req.mapping)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Invalid column mapping",
                "errors": [e.model_dump() for e in errors],
            },
        )

    rows = csv_import.iter_csv_rows(path)
    report = csv_import.normalize_rows(rows, req.mapping)
    if not report.events:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No valid rows could be imported",
                "errors": [e.model_dump() for e in report.errors[:20]],
            },
        )

    result = log_storage.persist_log(
        db,
        workspace_id=current_user.workspace_id,
        name=req.name,
        source="csv",
        events=report.events,
    )
    try:
        os.remove(path)
    except OSError:
        pass
    return result


@router.get("", response_model=list[EventLogOut])
def list_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EventLog]:
    stmt = (
        select(EventLog)
        .where(EventLog.workspace_id == current_user.workspace_id)
        .order_by(EventLog.imported_at.desc())
    )
    return list(db.scalars(stmt))


@router.get("/{log_id}", response_model=EventLogOut)
def get_log(
    log_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EventLog:
    return _get_owned_log(db, log_id, current_user)


@router.delete("/{log_id}", status_code=204)
def delete_log(
    log_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    if not log_storage.delete_log(db, log_id, current_user.workspace_id):
        raise HTTPException(status_code=404, detail="Log not found")
