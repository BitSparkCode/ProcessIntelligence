"""AI-assisted data linking / schema mapping (Story 6.1).

Suggests how raw CSV columns map onto the internal event-log fields. Uses the
LLM when configured, otherwise a deterministic name/value heuristic so the
import UI always gets a useful starting point.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.schemas.event_log import MappingSuggestion, SuggestedColumnMapping
from app.services.ai.llm import LLMClient, get_llm_client

_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}"  # 2024-01-01 12:00
    r"|\d{1,2}[/.]\d{1,2}[/.]\d{2,4}",  # 01/02/2024
)

# Column-name hints, ordered by priority. First match wins per field.
_NAME_HINTS: dict[str, tuple[str, ...]] = {
    "case_id": ("case", "case_id", "caseid", "trace", "order", "ticket", "incident", "process_id"),
    "activity": ("activity", "action", "event", "task", "step", "operation"),
    "timestamp": ("timestamp", "time", "date", "datetime", "when", "completed", "start"),
    "resource": ("resource", "user", "agent", "operator", "employee", "owner", "performer"),
    "cost": ("cost", "amount", "price", "value", "fee"),
    "lifecycle": ("lifecycle", "status", "state", "transition"),
}


def suggest_column_mapping(
    columns: list[str],
    rows: list[dict[str, str]],
    *,
    settings: Settings | None = None,
    client: LLMClient | None = None,
) -> MappingSuggestion:
    settings = settings or get_settings()
    client = client or get_llm_client(settings)

    if client.enabled:
        try:
            return _suggest_with_llm(columns, rows, client)
        except Exception:  # noqa: BLE001 - any failure falls back safely
            suggestion = _suggest_heuristic(columns, rows)
            suggestion.reasoning = (
                "AI request failed; fell back to heuristic column matching. "
                + suggestion.reasoning
            )
            return suggestion

    return _suggest_heuristic(columns, rows)


def _suggest_with_llm(
    columns: list[str], rows: list[dict[str, str]], client: LLMClient
) -> MappingSuggestion:
    sample = rows[:5]
    system = (
        "You map raw CSV columns onto a process-mining event log. "
        "The event log requires: case_id, activity, timestamp. "
        "Optional: resource, cost, lifecycle. "
        "Pick the best source column name for each field from the provided list, "
        "or null if none fits. Only use column names exactly as given."
    )
    user = (
        f"Columns: {columns}\n"
        f"Sample rows: {sample}\n\n"
        "Return JSON: {\"mapping\": {\"case_id\": str|null, \"activity\": str|null, "
        "\"timestamp\": str|null, \"resource\": str|null, \"cost\": str|null, "
        "\"lifecycle\": str|null}, \"confidence\": number 0..1, \"reasoning\": str}"
    )
    parsed = client.structured(system=system, user=user, schema=_LLMMappingResponse)
    mapping = _coerce_to_columns(parsed.mapping, columns)
    return MappingSuggestion(
        mapping=mapping,
        confidence=parsed.confidence,
        reasoning=parsed.reasoning or "Suggested by AI.",
        source="ai",
        ai_enabled=True,
    )


def _coerce_to_columns(
    mapping: SuggestedColumnMapping, columns: list[str]
) -> SuggestedColumnMapping:
    """Drop any hallucinated column names not present in the real CSV."""
    valid = set(columns)
    data = mapping.model_dump()
    for key in ("case_id", "activity", "timestamp", "resource", "cost", "lifecycle"):
        if data.get(key) not in valid:
            data[key] = None
    return SuggestedColumnMapping(**data)


def _suggest_heuristic(
    columns: list[str], rows: list[dict[str, str]]
) -> MappingSuggestion:
    chosen: dict[str, str] = {}
    taken: set[str] = set()
    lowered = {c: c.lower() for c in columns}

    for field, hints in _NAME_HINTS.items():
        best = _best_name_match(columns, lowered, hints, taken)
        if best is not None:
            chosen[field] = best
            taken.add(best)

    # If no timestamp matched by name, sniff column values for date-like content.
    if "timestamp" not in chosen:
        for col in columns:
            if col in taken:
                continue
            if _looks_like_timestamp(col, rows):
                chosen["timestamp"] = col
                taken.add(col)
                break

    required = {"case_id", "activity", "timestamp"}
    matched_required = required & chosen.keys()
    confidence = round(0.3 + 0.2 * len(matched_required), 2) if matched_required else 0.1

    return MappingSuggestion(
        mapping=SuggestedColumnMapping(**chosen),
        confidence=min(confidence, 0.9),
        reasoning="Matched columns by name keywords and value sniffing.",
        source="heuristic",
        ai_enabled=False,
    )


def _best_name_match(
    columns: list[str],
    lowered: dict[str, str],
    hints: tuple[str, ...],
    taken: set[str],
) -> str | None:
    # Exact-equality match first, then substring match, honoring hint priority.
    for hint in hints:
        for col in columns:
            if col not in taken and lowered[col] == hint:
                return col
    for hint in hints:
        for col in columns:
            if col not in taken and hint in lowered[col]:
                return col
    return None


def _looks_like_timestamp(col: str, rows: list[dict[str, str]]) -> bool:
    hits = 0
    seen = 0
    for row in rows[:10]:
        val = (row.get(col) or "").strip()
        if not val:
            continue
        seen += 1
        if _TIMESTAMP_RE.search(val):
            hits += 1
    return seen > 0 and hits / seen >= 0.6


class _LLMMappingResponse(BaseModel):
    mapping: SuggestedColumnMapping
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    reasoning: str = ""
