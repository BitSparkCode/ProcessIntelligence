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
    # Sprint 6 data prep: when set, the case id is built by concatenating these
    # columns (e.g. customer+order) instead of reading ``case_id``.
    case_id_columns: list[str] | None = Field(
        None, description="Composite case-id source columns"
    )
    # Normalize activity spelling variants (case/whitespace) onto the most
    # frequent spelling, merging e.g. 'Approve', 'approve ' into one activity.
    normalize_activities: bool = False
    # Keep only events whose lifecycle value is in this list (e.g. ["complete"]
    # to collapse start/complete pairs into single events).
    lifecycle_keep: list[str] | None = None


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


# ── AI data prep: dataset cleaning + case attribution (Sprint 6) ──────────────


class CaseAttribution(BaseModel):
    """How to attribute rows to cases when no clean case-id column exists."""

    kind: str = Field(
        ..., description="'single', 'composite' or 'none'"
    )
    columns: list[str] = Field(
        default_factory=list,
        description="Source columns forming the case id (order matters)",
    )
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    reasoning: str = ""


class CleaningSuggestion(BaseModel):
    severity: str = Field(..., description="'info', 'warning' or 'critical'")
    kind: str = Field(
        ...,
        description=(
            "'activity_variants', 'timestamp_format', 'empty_column', "
            "'duplicate_rows', 'missing_values', 'lifecycle_split' or 'other'"
        ),
    )
    target: str | None = Field(None, description="Column the suggestion applies to")
    message: str
    action: str | None = Field(
        None,
        description="Optional machine-readable fix, e.g. 'normalize_activities'",
    )


class DataPrepAdvice(BaseModel):
    """Cleaning + case-attribution advice for an uploaded dataset."""

    case_attribution: CaseAttribution
    cleaning: list[CleaningSuggestion] = Field(default_factory=list)
    source: str = "heuristic"  # heuristic | ai
    ai_enabled: bool = False
