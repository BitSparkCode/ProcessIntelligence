from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import EventLog, User
from app.schemas.analysis import (
    BottleneckReport,
    BottleneckRequest,
    ConformanceReport,
    ConformanceRequest,
    PerformanceReport,
    PerformanceRequest,
    VariantReport,
    VariantRequest,
)
from app.services import bottleneck, conformance, performance, variants
from app.services.conformance import ConformanceError

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


@router.post("/{log_id}/bottlenecks", response_model=BottleneckReport)
def detect_bottlenecks(
    log_id: str,
    params: BottleneckRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BottleneckReport:
    _get_owned_log(db, log_id, current_user)
    return bottleneck.detect_bottlenecks(db, log_id, params or BottleneckRequest())


@router.get("/{log_id}/bottlenecks/export", response_class=PlainTextResponse)
def export_bottlenecks(
    log_id: str,
    percentile: float = 90.0,
    top_n: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlainTextResponse:
    log = _get_owned_log(db, log_id, current_user)
    report = bottleneck.detect_bottlenecks(
        db, log_id, BottleneckRequest(percentile=percentile, top_n=top_n)
    )
    filename = f"{log.name or 'process'}-bottlenecks.txt"
    return PlainTextResponse(
        "\n".join(report.summary) + "\n",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{log_id}/conformance", response_model=ConformanceReport)
async def check_conformance(
    log_id: str,
    bpmn: UploadFile = File(..., description="Reference (soll) BPMN 2.0 model"),
    method: str = Form("alignment"),
    explain: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConformanceReport:
    _get_owned_log(db, log_id, current_user)
    fname = (bpmn.filename or "").lower()
    if not fname.endswith((".bpmn", ".xml")):
        raise HTTPException(
            status_code=400, detail="Only .bpmn / .xml reference models are supported"
        )
    if method not in ("alignment", "token"):
        raise HTTPException(status_code=422, detail="method must be 'alignment' or 'token'")

    raw = await bpmn.read()
    try:
        bpmn_xml = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="BPMN file must be UTF-8 text") from exc

    params = ConformanceRequest(method=method, explain=explain)
    try:
        return conformance.check_conformance(db, log_id, bpmn_xml, params)
    except ConformanceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
