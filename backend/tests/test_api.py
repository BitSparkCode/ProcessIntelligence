import io

SAMPLE_CSV = (
    "case,activity,time,who\n"
    "1,Register,2023-01-01 08:00:00,alice\n"
    "1,Review,2023-01-01 09:30:00,bob\n"
    "2,Register,2023-01-02 10:00:00,alice\n"
    "2,Review,2023-01-02 11:00:00,bob\n"
    "2,Archive,2023-01-02 12:00:00,carol\n"
)


def _upload(client, csv_text=SAMPLE_CSV, filename="log.csv"):
    return client.post(
        "/api/logs/upload",
        files={"file": (filename, io.BytesIO(csv_text.encode()), "text/csv")},
    )


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_upload_returns_preview(client):
    resp = _upload(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["preview"]["columns"] == ["case", "activity", "time", "who"]
    assert "upload_id" in body


def test_upload_rejects_non_csv(client):
    resp = client.post(
        "/api/logs/upload",
        files={"file": ("data.txt", io.BytesIO(b"x"), "text/plain")},
    )
    assert resp.status_code == 400


def test_full_import_flow(client):
    upload_id = _upload(client).json()["upload_id"]
    resp = client.post(
        "/api/logs/import",
        json={
            "upload_id": upload_id,
            "name": "My Log",
            "mapping": {
                "case_id": "case",
                "activity": "activity",
                "timestamp": "time",
                "resource": "who",
            },
        },
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["row_count"] == 5
    assert result["case_count"] == 2
    assert result["activity_count"] == 3

    logs = client.get("/api/logs").json()
    assert len(logs) == 1
    log_id = logs[0]["id"]
    assert client.get(f"/api/logs/{log_id}").json()["name"] == "My Log"

    assert client.delete(f"/api/logs/{log_id}").status_code == 204
    assert client.get("/api/logs").json() == []


def test_import_rejects_bad_mapping(client):
    upload_id = _upload(client).json()["upload_id"]
    resp = client.post(
        "/api/logs/import",
        json={
            "upload_id": upload_id,
            "name": "Bad",
            "mapping": {"case_id": "nope", "activity": "activity", "timestamp": "time"},
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["errors"][0]["code"] == "missing_column"
