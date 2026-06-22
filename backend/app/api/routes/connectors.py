"""Connector import API (Story 1.4).

Exposes the connector framework over HTTP: list available connectors and run a
SQL or REST import that lands directly in the caller's workspace event log.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.connectors import (
    ConnectorImportResult,
    ConnectorInfoOut,
    RestConnectorImportRequest,
    SqlConnectorImportRequest,
)
from app.services import log_storage
from app.services.connectors import (
    CONNECTORS,
    ConnectorError,
    RestConnector,
    RestConnectorConfig,
    SqlConnector,
    SqlConnectorConfig,
)
from app.services.connectors.base import BaseConnector

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


@router.get("", response_model=list[ConnectorInfoOut])
def list_connectors(
    current_user: User = Depends(get_current_user),
) -> list[ConnectorInfoOut]:
    return [
        ConnectorInfoOut(key=c.key, title=c.title, description=c.description)
        for c in CONNECTORS
    ]


def _import(
    db: Session, connector: BaseConnector, *, name: str, user: User
) -> ConnectorImportResult:
    try:
        result = connector.run()
    except ConnectorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not result.events:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No valid events extracted (pulled {result.extracted}, "
                f"skipped {result.skipped}). Check the query/URL and column mapping."
            ),
        )

    stored = log_storage.persist_log(
        db,
        workspace_id=user.workspace_id,
        name=name,
        source=connector.source_name,
        events=result.events,
    )
    return ConnectorImportResult(
        log_id=stored.log_id,
        name=stored.name,
        source=connector.source_name,
        extracted=result.extracted,
        skipped=result.skipped,
        row_count=stored.row_count,
        case_count=stored.case_count,
        activity_count=stored.activity_count,
    )


@router.post("/sql/import", response_model=ConnectorImportResult)
def import_from_sql(
    req: SqlConnectorImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConnectorImportResult:
    connector = SqlConnector(
        SqlConnectorConfig(
            connection_url=req.connection_url,
            query=req.query,
            mapping=req.mapping,
            max_rows=req.max_rows,
        )
    )
    return _import(db, connector, name=req.name, user=current_user)


@router.post("/rest/import", response_model=ConnectorImportResult)
def import_from_rest(
    req: RestConnectorImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConnectorImportResult:
    connector = RestConnector(
        RestConnectorConfig(
            url=req.url,
            mapping=req.mapping,
            method=req.method,
            headers=req.headers,
            params=req.params,
            json_body=req.json_body,
            records_path=req.records_path,
            timeout_seconds=req.timeout_seconds,
        )
    )
    return _import(db, connector, name=req.name, user=current_user)
