from datetime import datetime

from app.schemas.event_log import ColumnMapping
from app.services.csv_import import (
    normalize_rows,
    parse_cost,
    parse_timestamp,
    preview_csv,
    sniff_columns,
    validate_mapping,
)

# --- Three different CSV structures to exercise the mapping logic ----------------

STRUCTURE_A = """case,activity,time,who
1,Register,2023-01-01 08:00:00,alice
1,Review,2023-01-01 09:30:00,bob
2,Register,2023-01-02 10:00:00,alice
"""

# ISO-8601 with timezone, different column names, includes cost.
STRUCTURE_B = """CaseID;Step;When;Cost
A;Submit;2023-03-01T08:00:00+00:00;10.5
A;Approve;2023-03-01T12:00:00+00:00;20
"""

# European day-first date format, optional columns missing.
STRUCTURE_C = """order_id,task,ts
100,Create,01.02.2023 14:30
100,Ship,03.02.2023 09:15
"""


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_validate_mapping_detects_missing_columns():
    mapping = ColumnMapping(case_id="case", activity="activity", timestamp="missing_ts")
    errors = validate_mapping(["case", "activity", "time"], mapping)
    assert len(errors) == 1
    assert errors[0].code == "missing_column"
    assert errors[0].column == "missing_ts"


def test_validate_mapping_ok():
    mapping = ColumnMapping(case_id="case", activity="activity", timestamp="time", resource="who")
    assert validate_mapping(["case", "activity", "time", "who"], mapping) == []


def test_normalize_structure_a(tmp_path):
    path = _write(tmp_path, "a.csv", STRUCTURE_A)
    rows = list(__import_rows(path))
    mapping = ColumnMapping(case_id="case", activity="activity", timestamp="time", resource="who")
    report = normalize_rows(rows, mapping)
    assert len(report.events) == 3
    assert report.errors == []
    first = report.events[0]
    assert first.case_key == "1"
    assert first.activity == "Register"
    assert first.resource == "alice"
    assert first.timestamp == datetime(2023, 1, 1, 8, 0, 0)


def test_normalize_structure_b_semicolon_and_cost(tmp_path):
    path = _write(tmp_path, "b.csv", STRUCTURE_B)
    columns = sniff_columns_semicolon(path)
    assert columns == ["CaseID", "Step", "When", "Cost"]
    rows = list(__import_rows_semicolon(path))
    mapping = ColumnMapping(case_id="CaseID", activity="Step", timestamp="When", cost="Cost")
    report = normalize_rows(rows, mapping)
    assert len(report.events) == 2
    assert report.events[0].cost == 10.5
    assert report.events[1].cost == 20.0


def test_normalize_structure_c_dayfirst(tmp_path):
    path = _write(tmp_path, "c.csv", STRUCTURE_C)
    rows = list(__import_rows(path))
    mapping = ColumnMapping(
        case_id="order_id", activity="task", timestamp="ts", timestamp_format="%d.%m.%Y %H:%M"
    )
    report = normalize_rows(rows, mapping)
    assert len(report.events) == 2
    assert report.events[0].timestamp == datetime(2023, 2, 1, 14, 30)


def test_normalize_reports_bad_rows(tmp_path):
    content = "case,activity,time\n,Register,2023-01-01 08:00\n1,,2023-01-01 09:00\n1,Review,nope\n"
    path = _write(tmp_path, "bad.csv", content)
    rows = list(__import_rows(path))
    mapping = ColumnMapping(case_id="case", activity="activity", timestamp="time")
    report = normalize_rows(rows, mapping)
    assert report.events == []
    assert report.skipped_rows == 3
    codes = {e.code for e in report.errors}
    assert codes == {"empty_case_id", "empty_activity", "unparseable_timestamp"}


def test_preview_returns_header_and_rows(tmp_path):
    path = _write(tmp_path, "a.csv", STRUCTURE_A)
    preview = preview_csv(path, n=2)
    assert preview.columns == ["case", "activity", "time", "who"]
    assert preview.total_preview_rows == 2


def test_parse_timestamp_variants():
    assert parse_timestamp("2023-01-01 08:00:00") == datetime(2023, 1, 1, 8, 0, 0)
    assert parse_timestamp("") is None
    assert parse_timestamp("not a date") is None
    assert parse_timestamp("01.02.2023 14:30", "%d.%m.%Y %H:%M") == datetime(2023, 2, 1, 14, 30)


def test_parse_cost():
    assert parse_cost("10.5") == 10.5
    assert parse_cost("") is None
    assert parse_cost(None) is None
    assert parse_cost("abc") is None


def test_sniff_columns(tmp_path):
    path = _write(tmp_path, "a.csv", STRUCTURE_A)
    assert sniff_columns(path) == ["case", "activity", "time", "who"]


# --- helpers: comma vs semicolon CSV row iteration -----------------------------


def __import_rows(path):
    import csv

    with open(path, newline="", encoding="utf-8-sig") as fh:
        yield from csv.DictReader(fh)


def __import_rows_semicolon(path):
    import csv

    with open(path, newline="", encoding="utf-8-sig") as fh:
        yield from csv.DictReader(fh, delimiter=";")


def sniff_columns_semicolon(path):
    import csv

    with open(path, newline="", encoding="utf-8-sig") as fh:
        return next(csv.reader(fh, delimiter=";"))
