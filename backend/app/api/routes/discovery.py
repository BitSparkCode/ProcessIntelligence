from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import EventLog, User
from app.schemas.discovery import DiscoveryRequest, ProcessGraph
from app.services import discovery, inductive

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


def _get_owned_log(db: Session, log_id: str, user: User) -> EventLog:
    log = db.get(EventLog, log_id)
    if log is None or log.workspace_id != user.workspace_id:
        raise HTTPException(status_code=404, detail="Log not found")
    return log


@router.post("/{log_id}/heuristic-miner", response_model=ProcessGraph)
def heuristic_miner(
    log_id: str,
    params: DiscoveryRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProcessGraph:
    _get_owned_log(db, log_id, current_user)
    return discovery.discover_heuristic_net(db, log_id, params or DiscoveryRequest())


@router.post("/{log_id}/inductive-miner", response_model=ProcessGraph)
def inductive_miner(
    log_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProcessGraph:
    _get_owned_log(db, log_id, current_user)
    return inductive.discover_inductive_graph(db, log_id)


@router.get("/{log_id}/bpmn")
def export_bpmn(
    log_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    log = _get_owned_log(db, log_id, current_user)
    xml = inductive.export_bpmn(db, log_id)
    filename = f"{log.name or 'process'}.bpmn"
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
