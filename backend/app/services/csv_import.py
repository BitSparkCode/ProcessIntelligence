"""CSV import: preview, validation and streaming mapping to the internal event log.

The mapping logic is implemented as pure functions so it can be unit-tested without a
database or HTTP layer (see ``tests/test_csv_import.py``).
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from app.schemas.event_log import ColumnMapping, CsvPreview, ValidationError

REQUIRED_FIELDS = ("case_id", "activity", "timestamp")


@dataclass
class NormalizedEvent:
    case_key: str
    activity: str
    timestamp: datetime
    resource: str | None = None
    cost: float | None = None
    lifecycle: str | None = None


@dataclass
class NormalizationReport:
    events: list[NormalizedEvent] = field(default_factory=list)
    errors: list[ValidationError] = field(default_factory=list)
    skipped_rows: int = 0


def sniff_columns(file_path: str) -> list[str]:
    with open(file_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        try:
            return next(reader)
        except StopIteration:
            return []


def preview_csv(file_path: str, n: int = 20) -> CsvPreview:
    """Return the header and the first ``n`` data rows for the mapping UI."""
    rows: list[dict[str, str]] = []
    with open(file_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        columns = list(reader.fieldnames or [])
        for i, row in enumerate(reader):
            if i >= n:
                break
            rows.append({k: ("" if v is None else str(v)) for k, v in row.items()})
    return CsvPreview(columns=columns, rows=rows, total_preview_rows=len(rows))


def validate_mapping(columns: Iterable[str], mapping: ColumnMapping) -> list[ValidationError]:
    """Check that all mapped source columns exist in the CSV header."""
    errors: list[ValidationError] = []
    column_set = set(columns)
    mapped = {
        "case_id": mapping.case_id,
        "activity": mapping.activity,
        "timestamp": mapping.timestamp,
        "resource": mapping.resource,
        "cost": mapping.cost,
        "lifecycle": mapping.lifecycle,
    }
    for field_name, source in mapped.items():
        if source is None:
            continue
        if source not in column_set:
            errors.append(
                ValidationError(
                    code="missing_column",
                    message=f"Mapped column '{source}' for field '{field_name}' "
                    f"not found in CSV header",
                    column=source,
                )
            )
    return errors


def parse_timestamp(value: str, fmt: str | None = None) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    if fmt:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            return None
    parsed = pd.to_datetime(value, errors="coerce", utc=False)
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _opt_field(row: dict[str, str], column: str | None) -> str | None:
    if not column:
        return None
    raw = row.get(column)
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def parse_cost(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def event_from_record(
    record: dict[str, object], mapping: ColumnMapping
) -> NormalizedEvent | None:
    """Map a single source record (any dict) to a NormalizedEvent.

    Returns ``None`` when the record lacks a case id / activity or has an
    unparseable timestamp. Shared by the CSV importer and the connector
    framework (Story 1.4) so every source funnels through the same mapping.
    """
    row = {k: ("" if v is None else str(v)) for k, v in record.items()}
    case_key = (row.get(mapping.case_id) or "").strip()
    activity = (row.get(mapping.activity) or "").strip()
    if not case_key or not activity:
        return None
    ts = parse_timestamp(row.get(mapping.timestamp) or "", mapping.timestamp_format)
    if ts is None:
        return None
    return NormalizedEvent(
        case_key=case_key,
        activity=activity,
        timestamp=ts,
        resource=_opt_field(row, mapping.resource),
        cost=parse_cost(row.get(mapping.cost)) if mapping.cost else None,
        lifecycle=_opt_field(row, mapping.lifecycle),
    )


def normalize_rows(
    rows: Iterable[dict[str, str]],
    mapping: ColumnMapping,
    *,
    max_errors: int = 100,
) -> NormalizationReport:
    """Transform raw CSV rows into normalized events, collecting validation errors.

    Rows with empty case id or unparseable timestamp are skipped and reported.
    """
    report = NormalizationReport()
    for line_no, row in enumerate(rows, start=2):  # header is line 1
        case_key = (row.get(mapping.case_id) or "").strip()
        activity = (row.get(mapping.activity) or "").strip()
        ts_raw = row.get(mapping.timestamp) or ""

        if not case_key:
            report.skipped_rows += 1
            if len(report.errors) < max_errors:
                report.errors.append(
                    ValidationError(
                        code="empty_case_id",
                        message=f"Row {line_no}: empty Case ID",
                        column=mapping.case_id,
                    )
                )
            continue

        if not activity:
            report.skipped_rows += 1
            if len(report.errors) < max_errors:
                report.errors.append(
                    ValidationError(
                        code="empty_activity",
                        message=f"Row {line_no}: empty Activity",
                        column=mapping.activity,
                    )
                )
            continue

        ts = parse_timestamp(ts_raw, mapping.timestamp_format)
        if ts is None:
            report.skipped_rows += 1
            if len(report.errors) < max_errors:
                report.errors.append(
                    ValidationError(
                        code="unparseable_timestamp",
                        message=f"Row {line_no}: cannot parse timestamp '{ts_raw}'",
                        column=mapping.timestamp,
                    )
                )
            continue

        report.events.append(
            NormalizedEvent(
                case_key=case_key,
                activity=activity,
                timestamp=ts,
                resource=_opt_field(row, mapping.resource),
                cost=parse_cost(row.get(mapping.cost)) if mapping.cost else None,
                lifecycle=_opt_field(row, mapping.lifecycle),
            )
        )
    return report


def iter_csv_rows(file_path: str) -> Iterator[dict[str, str]]:
    """Stream rows from a CSV file one at a time (constant memory)."""
    with open(file_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield {k: ("" if v is None else v) for k, v in row.items()}
