import io

# 2 cases, 5 events, includes a resource column.
XES_CSV = (
    "case,activity,time,who\n"
    "1,A,2023-01-01 08:00:00,bob\n"
    "1,B,2023-01-01 09:00:00,sue\n"
    "1,C,2023-01-01 10:00:00,bob\n"
    "2,A,2023-01-02 08:00:00,sue\n"
    "2,C,2023-01-02 08:30:00,bob\n"
)


def _import_csv(client) -> str:
    up = client.post(
        "/api/logs/upload",
        files={"file": ("d.csv", io.BytesIO(XES_CSV.encode()), "text/csv")},
    ).json()["upload_id"]
    return client.post(
        "/api/logs/import",
        json={
            "upload_id": up,
            "name": "csv-source",
            "mapping": {
                "case_id": "case",
                "activity": "activity",
                "timestamp": "time",
                "resource": "who",
            },
        },
    ).json()["log_id"]


def test_xes_export_is_valid_xml(auth_client):
    log_id = _import_csv(auth_client)
    resp = auth_client.get(f"/api/logs/{log_id}/export/xes")
    assert resp.status_code == 200, resp.text
    assert "application/xml" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    body = resp.text
    assert "<log" in body and "concept:name" in body


def test_xes_round_trip_preserves_counts(auth_client):
    log_id = _import_csv(auth_client)
    xes_bytes = auth_client.get(f"/api/logs/{log_id}/export/xes").content

    resp = auth_client.post(
        "/api/logs/import-xes",
        files={"file": ("rt.xes", io.BytesIO(xes_bytes), "application/xml")},
        data={"name": "round-trip"},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["row_count"] == 5
    assert result["case_count"] == 2
    assert result["activity_count"] == 3


def test_import_xes_rejects_non_xes(auth_client):
    resp = auth_client.post(
        "/api/logs/import-xes",
        files={"file": ("d.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
        data={"name": "bad"},
    )
    assert resp.status_code == 400


def test_import_xes_requires_auth(client):
    resp = client.post(
        "/api/logs/import-xes",
        files={"file": ("rt.xes", io.BytesIO(b"<log/>"), "application/xml")},
        data={"name": "x"},
    )
    assert resp.status_code == 401
