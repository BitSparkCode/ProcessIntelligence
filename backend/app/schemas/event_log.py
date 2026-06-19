from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ColumnMapping(BaseModel):
    """Maps source CSV column names to the internal event-log fields."""

    case_id: str = Field(..., description="Source column holding the Case ID")
    activity: str = Field(..., description="Source column holding the Activity name")
    timestamp: str = Field(..., description="Source column holding the Timestamp")
    resource: str | None = Field(None, description="Optional Resource column")
    cost: str | None = Field(None, description="Optional activity cost column")
    lifecycle: str | None = Field(None, description="Optional lifecycle status column")
    # Optional explicit timestamp format (strftime). If omitted, inferred automatically.
    timestamp_format: str | None = None


class CsvPreview(BaseModel):
    columns: list[str]
    rows: list[dict[str, str]]
    total_preview_rows: int


class ImportResult(BaseModel):
    log_id: str
    name: str
    row_count: int
    case_count: int
    activity_count: int


class ValidationError(BaseModel):
    code: str
    message: str
    column: str | None = None


class EventLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    source: str
    imported_at: datetime
    row_count: int
    case_count: int


class SuggestedColumnMapping(BaseModel):
    """Like ColumnMapping but every field is optional (a suggestion may be partial)."""

    case_id: str | None = None
    activity: str | None = None
    timestamp: str | None = None
    resource: str | None = None
    cost: str | None = None
    lifecycle: str | None = None
    timestamp_format: str | None = None


class MappingSuggestion(BaseModel):
    """AI/heuristic-proposed column mapping for the import UI (Story 6.1)."""

    mapping: SuggestedColumnMapping
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    reasoning: str = ""
    source: str = "heuristic"  # heuristic | ai
    ai_enabled: bool = False
