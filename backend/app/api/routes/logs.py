from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import EventLog
from app.schemas.event_log import (
    ColumnMapping,
    CsvPreview,
    EventLogOut,
    ImportResult,
)
from app.services import csv_import, log_storage

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


class UploadResponse(BaseModel):
    upload_id: str
    preview: CsvPreview


class ImportRequest(BaseModel):
    upload_id: str
    name: str
    mapping: ColumnMapping


@router.post("/upload", response_model=UploadResponse)
async def upload_csv(file: UploadFile = File(...)) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")

    upload_id = str(uuid.uuid4())
    dest = _upload_path(upload_id)
    written = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(UPLOAD_CHUNK):
            written += len(chunk)
            if written > settings.max_upload_bytes:
                out.close()
                os.remove(dest)
                raise HTTPException(status_code=413, detail="File exceeds maximum upload size")
            out.write(chunk)

    preview = csv_import.preview_csv(dest)
    if not preview.columns:
        os.remove(dest)
        raise HTTPException(status_code=400, detail="CSV has no header row")
    return UploadResponse(upload_id=upload_id, preview=preview)


@router.post("/import", response_model=ImportResult)
def import_csv(req: ImportRequest, db: Session = Depends(get_db)) -> ImportResult:
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
        db, name=req.name, source="csv", events=report.events
    )
    try:
        os.remove(path)
    except OSError:
        pass
    return result


@router.get("", response_model=list[EventLogOut])
def list_logs(db: Session = Depends(get_db)) -> list[EventLog]:
    return list(db.scalars(select(EventLog).order_by(EventLog.imported_at.desc())))


@router.get("/{log_id}", response_model=EventLogOut)
def get_log(log_id: str, db: Session = Depends(get_db)) -> EventLog:
    log = db.get(EventLog, log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Log not found")
    return log


@router.delete("/{log_id}", status_code=204)
def delete_log(log_id: str, db: Session = Depends(get_db)) -> None:
    if not log_storage.delete_log(db, log_id):
        raise HTTPException(status_code=404, detail="Log not found")
