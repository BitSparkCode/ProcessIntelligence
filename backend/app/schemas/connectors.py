"""Request/response schemas for the connector import API (Story 1.4)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.event_log import ColumnMapping


class ConnectorInfoOut(BaseModel):
    key: str
    title: str
    description: str


class SqlConnectorImportRequest(BaseModel):
    name: str = Field(..., description="Name for the created event log")
    connection_url: str = Field(
        ..., description="SQLAlchemy URL, e.g. postgresql+psycopg2://user:pw@host/db"
    )
    query: str = Field(..., description="Read-only SELECT returning the event rows")
    mapping: ColumnMapping
    max_rows: int = Field(1_000_000, ge=1)


class RestConnectorImportRequest(BaseModel):
    name: str = Field(..., description="Name for the created event log")
    url: str
    mapping: ColumnMapping
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, str] = Field(default_factory=dict)
    json_body: dict | None = None
    records_path: str = Field(
        "", description="Dot-path to the records array (empty = response is the array)"
    )
    timeout_seconds: float = Field(30.0, gt=0)


class ConnectorImportResult(BaseModel):
    log_id: str
    name: str
    source: str
    extracted: int = Field(..., description="Raw records pulled from the source")
    skipped: int = Field(..., description="Records dropped (bad/missing fields)")
    row_count: int
    case_count: int
    activity_count: int
