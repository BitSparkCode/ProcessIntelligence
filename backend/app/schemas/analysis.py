"""Schemas for variant analysis (Story 2.4), the throughput dashboard
(Story 3.1), case inspection, log overview and simulation (Sprint 6)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.filters import LogFilter

# ── Variant analysis ──────────────────────────────────────────────────────────


class VariantRequest(BaseModel):
    top_n: int | None = Field(
        None, ge=1, description="Keep only the N most frequent variants"
    )
    min_frequency: int = Field(
        1, ge=1, description="Drop variants seen in fewer than this many cases"
    )
    filters: LogFilter | None = None


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
    filters: LogFilter | None = None


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


# ── Bottleneck detection (Story 3.2) ──────────────────────────────────────────


class BottleneckRequest(BaseModel):
    percentile: float = Field(
        90.0,
        ge=50.0,
        le=100.0,
        description="Flag steps whose mean waiting time exceeds this percentile "
        "of all individual waiting times",
    )
    window_days: int | None = Field(
        None, ge=1, description="Only consider cases within this many days of the latest event"
    )
    top_n: int = Field(5, ge=1, le=50, description="Size of the Top-N summary")
    filters: LogFilter | None = None


class Bottleneck(BaseModel):
    kind: str = Field(..., description="'transition' or 'activity'")
    label: str = Field(..., description="Human-readable, e.g. 'A → B' or 'A'")
    source: str
    target: str | None = None
    avg_waiting_seconds: float
    max_waiting_seconds: float
    frequency: int
    severity: float = Field(
        ..., description="avg waiting time as a multiple of the threshold (>= 1)"
    )


class BottleneckReport(BaseModel):
    log_id: str
    percentile: float
    threshold_seconds: float = Field(
        ..., description="The percentile cut-off over all waiting times"
    )
    case_count: int
    bottleneck_count: int
    bottlenecks: list[Bottleneck] = Field(
        ..., description="All flagged transitions/activities, slowest first"
    )
    top: list[Bottleneck] = Field(..., description="Top-N slowest, for the summary")
    summary: list[str] = Field(..., description="Plain-text Top-N lines, exportable")
    window_days: int | None = None


# ── Conformance checking (Story 3.3) ──────────────────────────────────────────


class ConformanceRequest(BaseModel):
    method: str = Field(
        "alignment",
        description="Fitness metric: 'alignment' (precise) or 'token' (fast). "
        "Per-case deviations are always derived from alignments.",
    )
    explain: bool = Field(
        False,
        description="Generate an AI/heuristic natural-language explanation of the "
        "deviations (Story 6.2)",
    )


class CaseDeviation(BaseModel):
    case_key: str
    fitness: float = Field(..., description="Trace fitness 0..1")
    is_fitting: bool
    deviations: list[str] = Field(
        default_factory=list, description="Plain-text deviation descriptions"
    )


class DeviationStat(BaseModel):
    kind: str = Field(..., description="'missing', 'unexpected' or 'order'")
    activity: str
    description: str
    case_count: int = Field(..., description="How many cases show this deviation")


class ConformanceReport(BaseModel):
    log_id: str
    method: str
    fitness: float = Field(..., description="Overall log fitness (0..1)")
    fitting_case_count: int
    case_count: int
    percentage_fitting: float = Field(..., description="Share of fully fitting cases (0..100)")
    deviation_summary: list[DeviationStat] = Field(
        ..., description="Deviations aggregated by activity, most frequent first"
    )
    case_deviations: list[CaseDeviation] = Field(
        ..., description="Per-case deviations, least conforming first"
    )
    explanation: str | None = Field(
        None, description="Natural-language deviation summary (Story 6.2)"
    )
    explanation_source: str | None = Field(
        None, description="'ai' or 'heuristic'"
    )


# ── Case inspector & replay (Sprint 6) ────────────────────────────────────────


class CaseListRequest(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)
    sort: str = Field(
        "start", description="'start', 'duration' or 'events'"
    )
    descending: bool = True
    search: str | None = Field(None, description="Substring match on the case id")
    filters: LogFilter | None = None


class CaseSummary(BaseModel):
    case_key: str
    start: datetime
    end: datetime
    duration_seconds: float
    event_count: int
    variant: list[str] = Field(..., description="Ordered activity names")


class CaseListReport(BaseModel):
    log_id: str
    total_cases: int
    page: int
    page_size: int
    cases: list[CaseSummary]


class CaseEventsRequest(BaseModel):
    case_key: str


class CaseEventOut(BaseModel):
    activity: str
    timestamp: datetime
    resource: str | None = None
    gap_to_next_seconds: float | None = None


class CaseDetailReport(BaseModel):
    log_id: str
    case_key: str
    duration_seconds: float
    events: list[CaseEventOut]


class ReplayRequest(BaseModel):
    filters: LogFilter | None = None
    max_cases: int = Field(
        500, ge=1, le=5000, description="Cap on replayed cases (most recent first)"
    )


class ReplayCase(BaseModel):
    case_key: str
    events: list[list[object]] = Field(
        ..., description="[activity, offset_seconds] pairs, offset from log start"
    )


class ReplayReport(BaseModel):
    log_id: str
    case_count: int
    horizon_seconds: float = Field(..., description="Full replay duration")
    cases: list[ReplayCase]


# ── Log overview dashboard (Sprint 6) ────────────────────────────────────────


class OverviewRequest(BaseModel):
    buckets: int = Field(
        30, ge=1, le=120, description="Time buckets for the cases-over-time series"
    )
    filters: LogFilter | None = None


class TimeBucket(BaseModel):
    start: datetime
    count: int


class NamedCount(BaseModel):
    name: str
    count: int


class OverviewReport(BaseModel):
    log_id: str
    case_count: int
    event_count: int
    activity_count: int
    resource_count: int
    variant_count: int
    first_event: datetime | None = None
    last_event: datetime | None = None
    mean_throughput_seconds: float = 0.0
    median_throughput_seconds: float = 0.0
    cases_over_time: list[TimeBucket]
    top_activities: list[NamedCount]
    top_resources: list[NamedCount]


# ── Process simulation (Sprint 6) ─────────────────────────────────────────────


class SimulationRequest(BaseModel):
    """What-if scenario simulated over the model discovered from the log."""

    cases: int = Field(
        1000, ge=1, le=20000, description="Number of cases to simulate"
    )
    arrival_rate_per_day: float | None = Field(
        None,
        gt=0,
        description="New cases per day; defaults to the observed rate",
    )
    arrival_rate_multiplier: float = Field(
        1.0, gt=0, le=100, description="Scales the arrival rate up/down"
    )
    default_servers: int | None = Field(
        None,
        ge=1,
        le=1000,
        description="If set, every activity is limited to this many parallel workers",
    )
    resource_pools: dict[str, int] = Field(
        default_factory=dict,
        description="activity -> number of parallel workers (overrides default)",
    )
    duration_multipliers: dict[str, float] = Field(
        default_factory=dict,
        description="activity -> service-time multiplier (e.g. 0.5 = twice as fast)",
    )
    global_duration_multiplier: float = Field(
        1.0, gt=0, le=100, description="Scales every activity's service time"
    )
    seed: int | None = Field(None, description="Fixed seed for reproducible runs")
    histogram_bins: int = Field(20, ge=1, le=100)
    filters: LogFilter | None = None


class DurationStats(BaseModel):
    mean_seconds: float
    median_seconds: float
    p90_seconds: float
    min_seconds: float
    max_seconds: float


class ActivitySimStat(BaseModel):
    activity: str
    executions: int
    servers: int | None = Field(None, description="None = unlimited capacity")
    mean_service_seconds: float
    mean_wait_seconds: float
    max_wait_seconds: float
    utilization: float | None = Field(
        None, description="Share of simulated time all servers were busy (0..1)"
    )
    observed_mean_seconds: float | None = Field(
        None, description="Observed mean time-at-activity in the log"
    )


class SimulationReport(BaseModel):
    log_id: str
    simulated_cases: int
    horizon_seconds: float
    arrival_rate_per_day: float
    baseline: DurationStats | None = Field(
        None, description="Observed case-duration stats from the log"
    )
    simulated: DurationStats
    histogram: list[HistogramBin]
    activity_stats: list[ActivitySimStat]
