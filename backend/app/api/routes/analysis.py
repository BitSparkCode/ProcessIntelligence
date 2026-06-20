from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import EventLog, User
from app.schemas.analysis import (
    PerformanceReport,
    PerformanceRequest,
    VariantReport,
    VariantRequest,
)
from app.services import performance, variants

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _get_owned_log(db: Session, log_id: str, user: User) -> EventLog:
    log = db.get(EventLog, log_id)
    if log is None or log.workspace_id != user.workspace_id:
        raise HTTPException(status_code=404, detail="Log not found")
    return log


@router.post("/{log_id}/variants", response_model=VariantReport)
def analyze_variants(
    log_id: str,
    params: VariantRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VariantReport:
    _get_owned_log(db, log_id, current_user)
    return variants.analyze_variants(db, log_id, params or VariantRequest())


@router.post("/{log_id}/performance", response_model=PerformanceReport)
def analyze_performance(
    log_id: str,
    params: PerformanceRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PerformanceReport:
    _get_owned_log(db, log_id, current_user)
    return performance.compute_performance(db, log_id, params or PerformanceRequest())
