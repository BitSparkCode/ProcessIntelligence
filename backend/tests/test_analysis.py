import io

# Variant 1 (A,B,C) occurs twice; variant 2 (A,C) occurs once.
ANALYSIS_CSV = (
    "case,activity,time\n"
    "1,A,2023-01-01 08:00:00\n"
    "1,B,2023-01-01 09:00:00\n"
    "1,C,2023-01-01 10:00:00\n"
    "2,A,2023-01-02 08:00:00\n"
    "2,B,2023-01-02 09:00:00\n"
    "2,C,2023-01-02 10:00:00\n"
    "3,A,2023-01-03 08:00:00\n"
    "3,C,2023-01-03 08:30:00\n"
)


def _import(client) -> str:
    up = client.post(
        "/api/logs/upload",
        files={"file": ("d.csv", io.BytesIO(ANALYSIS_CSV.encode()), "text/csv")},
    ).json()["upload_id"]
    return client.post(
        "/api/logs/import",
        json={
            "upload_id": up,
            "name": "analysis",
            "mapping": {"case_id": "case", "activity": "activity", "timestamp": "time"},
        },
    ).json()["log_id"]


def test_variants_ranked_by_frequency(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(f"/api/analysis/{log_id}/variants", json={})
    assert resp.status_code == 200, resp.text
    report = resp.json()

    assert report["case_count"] == 3
    assert report["variant_count"] == 2
    top = report["variants"][0]
    assert top["rank"] == 1
    assert top["sequence"] == ["A", "B", "C"]
    assert top["case_count"] == 2
    assert top["percentage"] == round(100 * 2 / 3, 2)
    # A->B->C spans two hours = 7200s.
    assert top["avg_throughput_seconds"] == 7200.0


def test_variants_min_frequency_filter(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/analysis/{log_id}/variants", json={"min_frequency": 2}
    )
    assert resp.status_code == 200
    variants = resp.json()["variants"]
    assert len(variants) == 1
    assert variants[0]["sequence"] == ["A", "B", "C"]


def test_variants_top_n_filter(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(f"/api/analysis/{log_id}/variants", json={"top_n": 1})
    assert resp.status_code == 200
    assert len(resp.json()["variants"]) == 1


def test_performance_kpis_and_histogram(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/analysis/{log_id}/performance", json={"histogram_bins": 4}
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()

    assert report["case_count"] == 3
    assert report["event_count"] == 8
    # Two cases take 7200s, one takes 1800s.
    assert report["max_throughput_seconds"] == 7200.0
    assert report["min_throughput_seconds"] == 1800.0
    assert report["median_throughput_seconds"] == 7200.0
    assert sum(b["count"] for b in report["histogram"]) == 3

    act = {a["activity"]: a for a in report["activity_stats"]}
    assert act["A"]["frequency"] == 3
    # A->next averages: (3600+3600+1800)/3 = 3000s.
    assert act["A"]["avg_duration_to_next_seconds"] == 3000.0


def test_bottlenecks_flagged_at_percentile(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(f"/api/analysis/{log_id}/bottlenecks", json={})
    assert resp.status_code == 200, resp.text
    report = resp.json()

    # Waiting times pooled: A->B/B->C are 3600s, A->C is 1800s. 90th pct = 3600s.
    assert report["percentile"] == 90.0
    assert report["threshold_seconds"] == 3600.0
    labels = {b["label"] for b in report["bottlenecks"]}
    # The slow 1-hour steps are flagged; the fast 30-min skip A->C is not.
    assert "A \u2192 B" in labels
    assert "B \u2192 C" in labels
    assert "A \u2192 C" not in labels
    assert report["bottleneck_count"] == len(report["bottlenecks"])

    top = report["top"][0]
    assert top["avg_waiting_seconds"] == 3600.0
    assert top["severity"] == 1.0
    assert any("percentile" in line for line in report["summary"])


def test_bottlenecks_export_is_text(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.get(f"/api/analysis/{log_id}/bottlenecks/export")
    assert resp.status_code == 200, resp.text
    assert "text/plain" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert "\u2192" in resp.text  # contains at least one "source -> target" line


def test_performance_requires_owned_log(client):
    from tests.conftest import register

    token_a = register(client, "pa@example.com")
    token_b = register(client, "pb@example.com")
    client.headers.update({"Authorization": f"Bearer {token_a}"})
    log_id = _import(client)

    client.headers.update({"Authorization": f"Bearer {token_b}"})
    assert client.post(f"/api/analysis/{log_id}/variants", json={}).status_code == 404
    assert (
        client.post(f"/api/analysis/{log_id}/performance", json={}).status_code == 404
    )
    assert (
        client.post(f"/api/analysis/{log_id}/bottlenecks", json={}).status_code == 404
    )
