"""Schemas for variant analysis (Story 2.4) and the throughput dashboard
(Story 3.1)."""

from __future__ import annotations

from pydantic import BaseModel, Field

# ── Variant analysis ──────────────────────────────────────────────────────────


class VariantRequest(BaseModel):
    top_n: int | None = Field(
        None, ge=1, description="Keep only the N most frequent variants"
    )
    min_frequency: int = Field(
        1, ge=1, description="Drop variants seen in fewer than this many cases"
    )


class Variant(BaseModel):
    rank: int
    sequence: list[str] = Field(..., description="Ordered activity names")
    case_count: int
    percentage: float = Field(..., description="Share of total cases (0..100)")
    avg_throughput_seconds: float = Field(
        ..., description="Mean case duration for this variant"
    )


class VariantReport(BaseModel):
    log_id: str
    case_count: int = Field(..., description="Total cases in the log")
    variant_count: int = Field(..., description="Distinct variants (before filters)")
    variants: list[Variant]


# ── Throughput / performance dashboard ────────────────────────────────────────


class PerformanceRequest(BaseModel):
    window_days: int | None = Field(
        None,
        ge=1,
        description="Only include cases that start within this many days of the "
        "most recent event",
    )
    histogram_bins: int = Field(
        10, ge=1, le=100, description="Number of throughput-time histogram bins"
    )


class ActivityStat(BaseModel):
    activity: str
    frequency: int
    avg_duration_to_next_seconds: float | None = Field(
        None, description="Mean waiting time from this activity to the next event"
    )


class TransitionStat(BaseModel):
    source: str
    target: str
    frequency: int
    avg_waiting_seconds: float


class HistogramBin(BaseModel):
    lower_seconds: float
    upper_seconds: float
    count: int


class PerformanceReport(BaseModel):
    log_id: str
    case_count: int
    event_count: int
    avg_throughput_seconds: float
    median_throughput_seconds: float
    min_throughput_seconds: float
    max_throughput_seconds: float
    activity_stats: list[ActivityStat]
    transition_stats: list[TransitionStat]
    histogram: list[HistogramBin]
    window_days: int | None = None
