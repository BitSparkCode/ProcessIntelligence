import sqlite3

import httpx
import pytest

from app.schemas.event_log import ColumnMapping
from app.services.connectors import (
    ConnectorError,
    RestConnector,
    RestConnectorConfig,
    SqlConnector,
    SqlConnectorConfig,
)

MAPPING = ColumnMapping(
    case_id="ticket", activity="action", timestamp="ts", resource="agent"
)


def _seed_sqlite(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE events (ticket TEXT, action TEXT, ts TEXT, agent TEXT)")
    conn.executemany(
        "INSERT INTO events VALUES (?, ?, ?, ?)",
        [
            ("T1", "Open", "2023-01-01 08:00:00", "alice"),
            ("T1", "Close", "2023-01-01 09:00:00", "bob"),
            ("T2", "Open", "2023-01-02 08:00:00", "alice"),
        ],
    )
    conn.commit()
    conn.close()


# ── SQL connector ─────────────────────────────────────────────────────────────


def test_sql_connector_extracts_events(tmp_path):
    db = tmp_path / "src.db"
    _seed_sqlite(str(db))
    connector = SqlConnector(
        SqlConnectorConfig(
            connection_url=f"sqlite:///{db}",
            query="SELECT ticket, action, ts, agent FROM events",
            mapping=MAPPING,
        )
    )
    result = connector.run()
    assert result.extracted == 3
    assert result.skipped == 0
    assert {e.case_key for e in result.events} == {"T1", "T2"}
    assert {e.activity for e in result.events} == {"Open", "Close"}
    assert result.events[0].resource == "alice"


def test_sql_connector_rejects_non_select():
    connector = SqlConnector(
        SqlConnectorConfig(
            connection_url="sqlite://",
            query="DELETE FROM events",
            mapping=MAPPING,
        )
    )
    with pytest.raises(ConnectorError):
        connector.validate()


def test_sql_connector_rejects_multiple_statements():
    connector = SqlConnector(
        SqlConnectorConfig(
            connection_url="sqlite://",
            query="SELECT 1; SELECT 2",
            mapping=MAPPING,
        )
    )
    with pytest.raises(ConnectorError):
        connector.validate()


# ── REST connector ────────────────────────────────────────────────────────────


def _mock_httpx(monkeypatch, payload: dict) -> None:
    def fake_request(method, url, **kwargs):
        return httpx.Response(200, json=payload, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", fake_request)


def test_rest_connector_extracts_nested_records(monkeypatch):
    payload = {
        "data": {
            "events": [
                {
                    "case": {"id": "C1"},
                    "step": "Submit",
                    "when": "2023-03-01T10:00:00Z",
                },
                {
                    "case": {"id": "C1"},
                    "step": "Approve",
                    "when": "2023-03-01T11:00:00Z",
                },
            ]
        }
    }
    _mock_httpx(monkeypatch, payload)
    connector = RestConnector(
        RestConnectorConfig(
            url="https://api.example.com/log",
            records_path="data.events",
            mapping=ColumnMapping(case_id="case.id", activity="step", timestamp="when"),
        )
    )
    result = connector.run()
    assert result.extracted == 2
    assert [e.activity for e in result.events] == ["Submit", "Approve"]
    assert all(e.case_key == "C1" for e in result.events)


def test_rest_connector_bad_records_path(monkeypatch):
    _mock_httpx(monkeypatch, {"data": {}})
    connector = RestConnector(
        RestConnectorConfig(
            url="https://api.example.com/log",
            records_path="data.events",
            mapping=ColumnMapping(case_id="a", activity="b", timestamp="c"),
        )
    )
    with pytest.raises(ConnectorError):
        connector.run()


def test_rest_connector_rejects_non_http_url():
    connector = RestConnector(
        RestConnectorConfig(
            url="ftp://example.com",
            mapping=ColumnMapping(case_id="a", activity="b", timestamp="c"),
        )
    )
    with pytest.raises(ConnectorError):
        connector.validate()


# ── API ───────────────────────────────────────────────────────────────────────


def test_list_connectors(auth_client):
    resp = auth_client.get("/api/connectors")
    assert resp.status_code == 200
    keys = {c["key"] for c in resp.json()}
    assert {"sql", "rest"} <= keys


def test_connectors_require_auth(client):
    assert client.get("/api/connectors").status_code == 401


def test_sql_import_end_to_end(auth_client, tmp_path):
    db = tmp_path / "src.db"
    _seed_sqlite(str(db))
    resp = auth_client.post(
        "/api/connectors/sql/import",
        json={
            "name": "from-sql",
            "connection_url": f"sqlite:///{db}",
            "query": "SELECT ticket, action, ts, agent FROM events",
            "mapping": {
                "case_id": "ticket",
                "activity": "action",
                "timestamp": "ts",
                "resource": "agent",
            },
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "sql"
    assert body["extracted"] == 3
    assert body["row_count"] == 3
    assert body["case_count"] == 2

    logs = auth_client.get("/api/logs").json()
    assert any(log["id"] == body["log_id"] for log in logs)


def test_sql_import_rejects_bad_query(auth_client):
    resp = auth_client.post(
        "/api/connectors/sql/import",
        json={
            "name": "bad",
            "connection_url": "sqlite://",
            "query": "DROP TABLE events",
            "mapping": {"case_id": "a", "activity": "b", "timestamp": "c"},
        },
    )
    assert resp.status_code == 422


def test_rest_import_end_to_end(auth_client, monkeypatch):
    payload = {
        "events": [
            {"cid": "R1", "act": "A", "t": "2023-04-01T08:00:00Z"},
            {"cid": "R1", "act": "B", "t": "2023-04-01T09:00:00Z"},
            {"cid": "R2", "act": "A", "t": "2023-04-02T08:00:00Z"},
        ]
    }
    _mock_httpx(monkeypatch, payload)
    resp = auth_client.post(
        "/api/connectors/rest/import",
        json={
            "name": "from-rest",
            "url": "https://api.example.com/events",
            "records_path": "events",
            "mapping": {"case_id": "cid", "activity": "act", "timestamp": "t"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "rest"
    assert body["row_count"] == 3
    assert body["case_count"] == 2
