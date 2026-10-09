"""Shared log filtering (Sprint 6, Disco-style filter panel).

One ``LogFilter`` payload is accepted by discovery, analysis and simulation
endpoints so the same filter state always produces the same case set.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LogFilter(BaseModel):
    """Filter applied to a stored log before any analysis runs.

    Semantics (matching Disco's filter families):
    - timeframe: keep cases whose first event falls inside [from_ts, to_ts]
    - endpoints: keep cases starting / ending with the selected activities
    - activities: include keeps only the listed activities; exclude drops them
    - resources: keep only events performed by the listed resources
    - performance: keep cases whose total duration is within the bounds
    Empty lists and None bounds mean "no restriction".
    """

    from_ts: datetime | None = Field(
        None, description="Keep cases starting at or after this instant"
    )
    to_ts: datetime | None = Field(
        None, description="Keep cases starting at or before this instant"
    )
    start_activities: list[str] = Field(
        default_factory=list,
        description="Keep only cases whose first activity is in this list",
    )
    end_activities: list[str] = Field(
        default_factory=list,
        description="Keep only cases whose last activity is in this list",
    )
    include_activities: list[str] = Field(
        default_factory=list,
        description="Keep only these activities (all others are removed)",
    )
    exclude_activities: list[str] = Field(
        default_factory=list,
        description="Remove these activities from every case",
    )
    resources: list[str] = Field(
        default_factory=list,
        description="Keep only events performed by these resources",
    )
    min_duration_seconds: float | None = Field(
        None, ge=0, description="Keep cases at least this long"
    )
    max_duration_seconds: float | None = Field(
        None, ge=0, description="Keep cases at most this long"
    )
