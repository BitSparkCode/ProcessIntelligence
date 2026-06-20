from __future__ import annotations

from pydantic import BaseModel, Field


class DiscoveryRequest(BaseModel):
    """Parameters for Heuristic Miner discovery (Story 2.1)."""

    dependency_threshold: float = Field(
        0.5, ge=0.0, le=1.0, description="Min dependency measure to keep an edge"
    )
    frequency_threshold: int = Field(
        1, ge=1, description="Min directly-follows frequency to keep an edge"
    )


class ActivityNode(BaseModel):
    id: str
    label: str
    frequency: int = Field(..., description="Number of events for this activity")
    is_start: bool = False
    is_end: bool = False
    avg_duration_seconds: float | None = Field(
        None, description="Avg time from this activity to its successors"
    )


class ProcessEdge(BaseModel):
    source: str
    target: str
    frequency: int = Field(..., description="Directly-follows count")
    dependency: float = Field(..., description="Heuristic dependency measure 0..1")
    avg_duration_seconds: float = Field(
        0.0, description="Avg time between source and target events"
    )


class ProcessGraph(BaseModel):
    """A discovered process model rendered as a directed graph (DFG)."""

    log_id: str
    algorithm: str = Field(
        "heuristic", description="Discovery algorithm: heuristic | inductive"
    )
    nodes: list[ActivityNode]
    edges: list[ProcessEdge]
    case_count: int
    event_count: int
    start_activities: list[str]
    end_activities: list[str]
    dependency_threshold: float
    frequency_threshold: int
