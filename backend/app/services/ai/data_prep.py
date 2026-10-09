"""AI-assisted dataset cleaning and case attribution (Sprint 6).

Profiles an uploaded CSV and returns a ``DataPrepAdvice``: which column(s)
should form the case id (single or composite key), plus a list of cleaning
suggestions (activity-name variants, timestamp issues, empty/constant columns,
duplicates, lifecycle split). Uses the LLM when configured and always falls
back to deterministic heuristics so the import UI is useful offline.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.schemas.event_log import (
    CaseAttribution,
    CleaningSuggestion,
    DataPrepAdvice,
)
from app.services.ai.llm import LLMClient, get_llm_client

_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}"
    r"|\d{1,2}[/.]\d{1,2}[/.]\d{2,4}"
)
_WS_RE = re.compile(r"\s+")

# Name hints for columns likely to hold a case identifier on their own.
_CASE_HINTS = (
    "case", "case_id", "caseid", "trace", "order", "ticket",
    "incident", "process_id", "invoice", "request", "claim",
)
_LIFECYCLE_WORDS = {
    "start", "complete", "scheduled", "assign", "abort", "suspend", "resume",
    "withdraw", "autoskip", "manualskip", "ate_abort", "pi_abort",
}
_ACTIVITY_HINTS = (
    "activity", "action", "task", "step", "operation", "event", "status",
)

PROFILE_SAMPLE_ROWS = 200


def _column_profile(
    columns: list[str], rows: list[dict[str, str]]
) -> dict[str, dict[str, Any]]:
    """Deterministic per-column stats used by both heuristic and AI paths."""
    profile: dict[str, dict[str, Any]] = {}
    total = len(rows) or 1
    for col in columns:
        values = [(row.get(col) or "").strip() for row in rows]
        non_empty = [v for v in values if v]
        distinct = len(set(non_empty))
        ts_hits = sum(1 for v in non_empty[:50] if _TIMESTAMP_RE.search(v))
        numeric_hits = sum(
            1 for v in non_empty[:50] if re.fullmatch(r"-?\d+([.,]\d+)?", v)
        )
        profile[col] = {
            "non_empty": len(non_empty),
            "empty_ratio": round(1 - len(non_empty) / total, 3),
            "distinct": distinct,
            "distinct_ratio": round(distinct / max(len(non_empty), 1), 3),
            "looks_timestamp": ts_hits >= 0.6 * min(len(non_empty), 50) > 0,
            "looks_numeric": numeric_hits >= 0.8 * min(len(non_empty), 50) > 0,
            "constant": distinct == 1,
            "samples": list(dict.fromkeys(non_empty[:5]))[:5],
        }
    return profile


def _case_candidates(
    columns: list[str], rows: list[dict[str, str]], ts_col: str | None
) -> list[str]:
    return [
        c
        for c in columns
        if c != ts_col
    ]


def _attribute_case_id(
    columns: list[str], rows: list[dict[str, str]]
) -> CaseAttribution:
    """Pick single column or best composite key for case attribution.

    A key (single column or column pair) is plausible when its groups recur:
    a real case has several events, so avg rows-per-key should be >= ~1.5,
    and no single key may dominate the whole dataset.
    """
    if not rows or not columns:
        return CaseAttribution(kind="none", reasoning="No data to inspect.")

    n = len(rows)
    profile = _column_profile(columns, rows)

    def group_stats(cols: list[str]) -> tuple[int, float, float]:
        combos = Counter(
            tuple((row.get(c) or "").strip() for c in cols) for row in rows
        )
        sizes = list(combos.values())
        return len(combos), n / len(combos), max(sizes) / n

    usable = [
        c
        for c in columns
        if not profile[c]["looks_timestamp"]
        and int(profile[c]["distinct"]) >= 2
        # The activity column itself is never part of the case key.
        and not any(h in c.lower() for h in _ACTIVITY_HINTS)
    ]
    if not usable:
        return CaseAttribution(kind="none", reasoning="No usable case identifier.")

    # Single-column match by name hint (a real case id groups several events).
    for hint in _CASE_HINTS:
        for col in usable:
            if hint in col.lower():
                combos, avg_size, _ = group_stats([col])
                if avg_size >= 1.5:
                    return CaseAttribution(
                        kind="single",
                        columns=[col],
                        confidence=0.85,
                        reasoning=(
                            f"Column '{col}' looks like a case identifier "
                            f"({combos} distinct keys across {n} rows)."
                        ),
                    )

    single_scores: dict[str, int] = {}
    for col in usable:
        combos, avg_size, share = group_stats([col])
        if avg_size >= 1.5 and share < 0.9:
            single_scores[col] = combos
    best_single = (
        max(single_scores, key=lambda c: single_scores[c])
        if single_scores
        else None
    )

    pair_scores: dict[tuple[str, str], int] = {}
    for a, b in itertools.combinations(usable, 2):
        if profile[a]["distinct_ratio"] > 0.95 or profile[b]["distinct_ratio"] > 0.95:
            continue
        combos, avg_size, share = group_stats([a, b])
        if avg_size >= 1.5 and share < 0.9:
            pair_scores[(a, b)] = combos
    best_pair = (
        max(pair_scores, key=lambda p: pair_scores[p]) if pair_scores else None
    )

    # Prefer a composite key when it splits the data into markedly more,
    # still-recurring groups than any single column does.
    if best_pair and (
        best_single is None
        or pair_scores[best_pair] > 1.5 * single_scores[best_single]
    ):
        return CaseAttribution(
            kind="composite",
            columns=list(best_pair),
            confidence=0.6,
            reasoning=(
                f"No single case-id column found; combining "
                f"'{best_pair[0]}' + '{best_pair[1]}' yields "
                f"{pair_scores[best_pair]} recurring keys."
            ),
        )
    if best_single:
        return CaseAttribution(
            kind="single",
            columns=[best_single],
            confidence=0.45,
            reasoning=(
                f"No obvious case-id column; '{best_single}' has the best "
                f"group structure ({single_scores[best_single]} recurring keys)."
            ),
        )
    if best_pair:
        return CaseAttribution(
            kind="composite",
            columns=list(best_pair),
            confidence=0.5,
            reasoning=(
                f"Combining '{best_pair[0]}' + '{best_pair[1]}' yields "
                f"{pair_scores[best_pair]} recurring keys."
            ),
        )
    return CaseAttribution(kind="none", reasoning="No usable case identifier.")


def _cleaning_suggestions(
    columns: list[str], rows: list[dict[str, str]]
) -> list[CleaningSuggestion]:
    profile = _column_profile(columns, rows)
    suggestions: list[CleaningSuggestion] = []

    for col, stats in profile.items():
        if stats["empty_ratio"] == 1:
            suggestions.append(
                CleaningSuggestion(
                    severity="info",
                    kind="empty_column",
                    target=col,
                    message=f"Column '{col}' is empty in every sampled row; "
                    "leave it unmapped.",
                )
            )
        elif stats["constant"]:
            suggestions.append(
                CleaningSuggestion(
                    severity="info",
                    kind="empty_column",
                    target=col,
                    message=f"Column '{col}' has a single constant value; "
                    "it adds no information to the log.",
                )
            )

    # Timestamp columns that fail to parse cleanly.
    for col, stats in profile.items():
        if stats["looks_timestamp"]:
            bad = sum(
                1
                for row in rows
                if (row.get(col) or "").strip()
                and not _TIMESTAMP_RE.search(row.get(col) or "")
            )
            if bad:
                suggestions.append(
                    CleaningSuggestion(
                        severity="warning",
                        kind="timestamp_format",
                        target=col,
                        message=(
                            f"{bad} sampled values in '{col}' do not match a "
                            "common timestamp shape; consider an explicit "
                            "timestamp format."
                        ),
                        action="set_timestamp_format",
                    )
                )

    # Activity-name variants (same name with different case/whitespace).
    for col in columns:
        if "activity" in col.lower() or "task" in col.lower() or "step" in col.lower():
            spellings: dict[str, Counter[str]] = {}
            for row in rows:
                raw = (row.get(col) or "").strip()
                if not raw:
                    continue
                key = _WS_RE.sub(" ", raw).lower()
                spellings.setdefault(key, Counter())[raw] += 1
            dup = {k: dict(v) for k, v in spellings.items() if len(v) > 1}
            if dup:
                examples = "; ".join(
                    " / ".join(v.keys()) for v in list(dup.values())[:3]
                )
                suggestions.append(
                    CleaningSuggestion(
                        severity="warning",
                        kind="activity_variants",
                        target=col,
                        message=(
                            f"'{col}' mixes spelling variants "
                            f"({examples}); merge them into one activity."
                        ),
                        action="normalize_activities",
                    )
                )

    # Lifecycle column that splits events into start/complete pairs.
    for col in columns:
        if "lifecycle" in col.lower() or "transition" in col.lower():
            vals = {
                (row.get(col) or "").strip().lower() for row in rows
            } - {""}
            if vals & _LIFECYCLE_WORDS and len(vals) > 1:
                suggestions.append(
                    CleaningSuggestion(
                        severity="warning",
                        kind="lifecycle_split",
                        target=col,
                        message=(
                            f"'{col}' carries lifecycle transitions "
                            f"({', '.join(sorted(vals))}); keep one transition "
                            "(e.g. 'complete') to avoid doubled events."
                        ),
                        action="filter_lifecycle",
                    )
                )

    # Missing values in required-ish columns.
    for col in columns:
        ratio = float(profile[col]["empty_ratio"])
        if 0 < ratio < 1 and profile[col]["distinct"] > 1:
            if profile[col]["empty_ratio"] >= 0.05:
                suggestions.append(
                    CleaningSuggestion(
                        severity="info",
                        kind="missing_values",
                        target=col,
                        message=(
                            f"'{col}' is empty in {ratio:.0%} of sampled rows; "
                            "rows with empty case id or activity are skipped."
                        ),
                    )
                )

    # Fully duplicated rows.
    seen_rows: set[tuple[str, ...]] = set()
    dup_count = 0
    for row in rows:
        row_key = tuple((row.get(c) or "") for c in columns)
        if row_key in seen_rows:
            dup_count += 1
        else:
            seen_rows.add(row_key)
    if dup_count:
        suggestions.append(
            CleaningSuggestion(
                severity="warning",
                kind="duplicate_rows",
                target=None,
                message=(
                    f"{dup_count} fully duplicated rows in the sample; "
                    "deduplicate before import to avoid double-counted events."
                ),
            )
        )
    return suggestions


class _LLMPrepResponse(BaseModel):
    case_attribution: CaseAttribution
    cleaning: list[CleaningSuggestion] = Field(default_factory=list)


def suggest_prep(
    columns: list[str],
    rows: list[dict[str, str]],
    *,
    settings: Settings | None = None,
    client: LLMClient | None = None,
) -> DataPrepAdvice:
    settings = settings or get_settings()
    client = client or get_llm_client(settings)

    heuristic = DataPrepAdvice(
        case_attribution=_attribute_case_id(columns, rows),
        cleaning=_cleaning_suggestions(columns, rows),
        source="heuristic",
        ai_enabled=client.enabled,
    )

    if not client.enabled:
        return heuristic

    try:
        profile = _column_profile(columns, rows)
        system = (
            "You prepare a raw CSV dataset for process mining. "
            "Decide which column(s) identify a case (one event sequence): "
            "either a single id column or a composite key of several columns. "
            "Then list concrete data-cleaning issues. Only reference column "
            "names exactly as provided."
        )
        user = (
            f"Columns: {columns}\n"
            f"Column profile: {profile}\n"
            f"Sample rows: {rows[:5]}\n\n"
            "Return JSON: {\"case_attribution\": {\"kind\": \"single\"|"
            "\"composite\"|\"none\", \"columns\": [str], \"confidence\": 0..1, "
            "\"reasoning\": str}, \"cleaning\": [{\"severity\": \"info\"|"
            "\"warning\"|\"critical\", \"kind\": str, \"target\": str|null, "
            "\"message\": str, \"action\": str|null}]}"
        )
        parsed = client.structured(
            system=system, user=user, schema=_LLMPrepResponse
        )
        valid = set(columns)
        cols = [c for c in parsed.case_attribution.columns if c in valid]
        attribution = parsed.case_attribution
        if len(cols) != len(attribution.columns):
            attribution = CaseAttribution(
                kind=heuristic.case_attribution.kind,
                columns=heuristic.case_attribution.columns,
                confidence=heuristic.case_attribution.confidence,
                reasoning=heuristic.case_attribution.reasoning,
            )
        else:
            attribution.columns = cols
        # Merge AI suggestions with heuristic ones the model missed.
        seen = {(s.kind, s.target) for s in parsed.cleaning}
        merged = list(parsed.cleaning) + [
            s for s in heuristic.cleaning if (s.kind, s.target) not in seen
        ]
        return DataPrepAdvice(
            case_attribution=attribution,
            cleaning=merged,
            source="ai",
            ai_enabled=True,
        )
    except Exception:  # noqa: BLE001 - any failure falls back safely
        heuristic.ai_enabled = True
        return heuristic
