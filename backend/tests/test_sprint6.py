"""Sprint 6: log filters, case inspector, replay, overview, simulation,
AI data prep (cleaning + case attribution)."""

import io

LOG_CSV = (
    "case,activity,time,who\n"
    "1,A,2023-01-01 08:00:00,alice\n"
    "1,B,2023-01-01 09:00:00,bob\n"
    "1,C,2023-01-01 10:00:00,carol\n"
    "2,A,2023-01-02 08:00:00,alice\n"
    "2,B,2023-01-02 09:00:00,bob\n"
    "2,C,2023-01-02 10:00:00,carol\n"
    "3,A,2023-01-03 08:00:00,alice\n"
    "3,C,2023-01-03 08:30:00,carol\n"
)

MAPPING = {
    "case_id": "case",
    "activity": "activity",
    "timestamp": "time",
    "resource": "who",
}


def _import(client, csv_text: str = LOG_CSV, mapping: dict | None = None) -> str:
    up = client.post(
        "/api/logs/upload",
        files={"file": ("d.csv", io.BytesIO(csv_text.encode()), "text/csv")},
    ).json()["upload_id"]
    return client.post(
        "/api/logs/import",
        json={
            "upload_id": up,
            "name": "sprint6",
            "mapping": mapping or MAPPING,
        },
    ).json()["log_id"]


# ── Filters ───────────────────────────────────────────────────────────────────


def test_filter_exclude_activity(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/analysis/{log_id}/variants",
        json={"filters": {"exclude_activities": ["B"]}},
    )
    assert resp.status_code == 200
    seqs = [v["sequence"] for v in resp.json()["variants"]]
    assert seqs == [["A", "C"]]
    assert resp.json()["case_count"] == 3


def test_filter_endpoints(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/analysis/{log_id}/performance",
        json={"filters": {"end_activities": ["C"]}},
    )
    assert resp.status_code == 200
    assert resp.json()["case_count"] == 3

    resp = auth_client.post(
        f"/api/analysis/{log_id}/performance",
        json={"filters": {"end_activities": ["B"]}},
    )
    assert resp.json()["case_count"] == 0


def test_filter_timeframe(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/analysis/{log_id}/performance",
        json={
            "filters": {
                "from_ts": "2023-01-02T00:00:00Z",
                "to_ts": "2023-01-02T23:59:59Z",
            }
        },
    )
    assert resp.json()["case_count"] == 1


def test_filter_performance_duration(auth_client):
    log_id = _import(auth_client)
    # case 3 is 30 minutes; cases 1-2 are 2 hours
    resp = auth_client.post(
        f"/api/analysis/{log_id}/variants",
        json={"filters": {"max_duration_seconds": 3600}},
    )
    body = resp.json()
    assert body["case_count"] == 1
    assert body["variants"][0]["sequence"] == ["A", "C"]


def test_filter_resource(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/analysis/{log_id}/variants",
        json={"filters": {"resources": ["carol"]}},
    )
    body = resp.json()
    assert body["case_count"] == 3
    assert all(v["sequence"] == ["C"] for v in body["variants"])


def test_filtered_discovery(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/discovery/{log_id}/heuristic-miner",
        json={"filters": {"exclude_activities": ["B"]}},
    )
    assert resp.status_code == 200
    labels = {n["label"] for n in resp.json()["nodes"]}
    assert labels == {"A", "C"}


# ── Case inspector, replay, overview ──────────────────────────────────────────


def test_cases_list_and_detail(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(f"/api/analysis/{log_id}/cases", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_cases"] == 3
    assert {c["case_key"] for c in body["cases"]} == {"1", "2", "3"}

    detail = auth_client.post(
        f"/api/analysis/{log_id}/case-events", json={"case_key": "1"}
    )
    assert detail.status_code == 200
    events = detail.json()["events"]
    assert [e["activity"] for e in events] == ["A", "B", "C"]
    assert events[0]["gap_to_next_seconds"] == 3600.0
    assert events[-1]["gap_to_next_seconds"] is None


def test_cases_search_and_pagination(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/analysis/{log_id}/cases",
        json={"search": "2", "page": 1, "page_size": 1},
    )
    body = resp.json()
    assert body["total_cases"] == 1
    assert body["cases"][0]["case_key"] == "2"


def test_case_detail_unknown_404(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/analysis/{log_id}/case-events", json={"case_key": "nope"}
    )
    assert resp.status_code == 404


def test_replay_payload(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(f"/api/analysis/{log_id}/replay", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["case_count"] == 3
    assert body["horizon_seconds"] > 0
    case = next(c for c in body["cases"] if c["case_key"] == "1")
    assert [e[0] for e in case["events"]] == ["A", "B", "C"]
    assert case["events"][0][1] == 0.0


def test_overview(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(f"/api/analysis/{log_id}/overview", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["case_count"] == 3
    assert body["event_count"] == 8
    assert body["activity_count"] == 3
    assert body["variant_count"] == 2
    assert body["cases_over_time"]
    assert body["top_activities"][0]["name"] == "A"


# ── Simulation ────────────────────────────────────────────────────────────────


def test_simulation_deterministic_and_completes(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/analysis/{log_id}/simulate", json={"cases": 50, "seed": 7}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["simulated_cases"] == 50
    assert body["arrival_rate_per_day"] > 0
    assert body["baseline"]["mean_seconds"] > 0
    assert body["simulated"]["mean_seconds"] > 0
    assert body["histogram"]
    acts = {a["activity"] for a in body["activity_stats"]}
    assert {"A", "B", "C"} <= acts

    same = auth_client.post(
        f"/api/analysis/{log_id}/simulate", json={"cases": 50, "seed": 7}
    ).json()
    assert same["simulated"] == body["simulated"]


def test_simulation_resource_pool_creates_waiting(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/analysis/{log_id}/simulate",
        json={
            "cases": 200,
            "seed": 1,
            "arrival_rate_per_day": 50,
            "resource_pools": {"A": 1},
        },
    )
    body = resp.json()
    stat = next(a for a in body["activity_stats"] if a["activity"] == "A")
    assert stat["servers"] == 1
    assert stat["mean_wait_seconds"] > 0
    assert 0 < stat["utilization"] <= 1


def test_simulation_duration_multiplier_slows_down(auth_client):
    log_id = _import(auth_client)
    base = auth_client.post(
        f"/api/analysis/{log_id}/simulate", json={"cases": 100, "seed": 5}
    ).json()
    slow = auth_client.post(
        f"/api/analysis/{log_id}/simulate",
        json={
            "cases": 100,
            "seed": 5,
            "duration_multipliers": {"B": 4.0},
        },
    ).json()
    assert slow["simulated"]["mean_seconds"] > base["simulated"]["mean_seconds"]


# ── AI data prep ──────────────────────────────────────────────────────────────


def test_prep_advice_single_case_column(auth_client):
    up = auth_client.post(
        "/api/logs/upload",
        files={"file": ("d.csv", io.BytesIO(LOG_CSV.encode()), "text/csv")},
    ).json()["upload_id"]
    resp = auth_client.post("/api/logs/prep-advice", json={"upload_id": up})
    assert resp.status_code == 200
    body = resp.json()
    assert body["case_attribution"]["kind"] == "single"
    assert body["case_attribution"]["columns"] == ["case"]


def test_prep_advice_composite_case_id(auth_client):
    # No single column identifies a case: batches repeat per line, so only
    # line+batch together give a unique case key.
    rows = "line,batch,step,when\n" + "".join(
        f"l{i % 3},b{i % 10},step{j % 4},2023-01-0{j + 1} 08:00:00\n"
        for i in range(30)
        for j in range(4)
    )
    up = auth_client.post(
        "/api/logs/upload",
        files={"file": ("d.csv", io.BytesIO(rows.encode()), "text/csv")},
    ).json()["upload_id"]
    body = auth_client.post(
        "/api/logs/prep-advice", json={"upload_id": up}
    ).json()
    attr = body["case_attribution"]
    assert attr["kind"] == "composite"
    assert set(attr["columns"]) == {"line", "batch"}


def test_prep_advice_detects_activity_variants(auth_client):
    csv_text = (
        "case,activity,time\n"
        "1,Approve,2023-01-01 08:00\n"
        "1,approve ,2023-01-01 09:00\n"
        "2,APPROVE,2023-01-02 08:00\n"
        "2,Approve,2023-01-02 09:00\n"
    )
    up = auth_client.post(
        "/api/logs/upload",
        files={"file": ("d.csv", io.BytesIO(csv_text.encode()), "text/csv")},
    ).json()["upload_id"]
    body = auth_client.post(
        "/api/logs/prep-advice", json={"upload_id": up}
    ).json()
    kinds = {s["kind"] for s in body["cleaning"]}
    assert "activity_variants" in kinds
    sug = next(s for s in body["cleaning"] if s["kind"] == "activity_variants")
    assert sug["action"] == "normalize_activities"


def test_prep_advice_unknown_upload_404(auth_client):
    resp = auth_client.post(
        "/api/logs/prep-advice",
        json={"upload_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


def test_composite_case_id_import(auth_client):
    csv_text = (
        "customer,order,activity,time\n"
        "c1,o9,A,2023-01-01 08:00\n"
        "c1,o9,B,2023-01-01 09:00\n"
        "c2,o7,A,2023-01-01 10:00\n"
    )
    log_id = _import(
        auth_client,
        csv_text,
        {
            "case_id": "customer",
            "case_id_columns": ["customer", "order"],
            "activity": "activity",
            "timestamp": "time",
        },
    )
    cases = auth_client.post(
        f"/api/analysis/{log_id}/cases", json={}
    ).json()
    assert cases["total_cases"] == 2
    keys = {c["case_key"] for c in cases["cases"]}
    assert keys == {"c1 | o9", "c2 | o7"}


def test_normalize_activities_import(auth_client):
    csv_text = (
        "case,activity,time\n"
        "1,Approve,2023-01-01 08:00\n"
        "1,approve ,2023-01-01 09:00\n"
        "2,APPROVE,2023-01-02 08:00\n"
        "2,Approve,2023-01-02 09:00\n"
    )
    log_id = _import(
        auth_client,
        csv_text,
        {
            "case_id": "case",
            "activity": "activity",
            "timestamp": "time",
            "normalize_activities": True,
        },
    )
    overview = auth_client.post(
        f"/api/analysis/{log_id}/overview", json={}
    ).json()
    assert overview["activity_count"] == 1
    # Canonical spelling is the most frequent variant.
    assert overview["top_activities"][0]["name"] == "Approve"


def test_lifecycle_keep_import(auth_client):
    csv_text = (
        "case,activity,time,transition\n"
        "1,A,2023-01-01 08:00,start\n"
        "1,A,2023-01-01 09:00,complete\n"
        "1,B,2023-01-01 10:00,complete\n"
    )
    log_id = _import(
        auth_client,
        csv_text,
        {
            "case_id": "case",
            "activity": "activity",
            "timestamp": "time",
            "lifecycle": "transition",
            "lifecycle_keep": ["complete"],
        },
    )
    cases = auth_client.post(
        f"/api/analysis/{log_id}/cases", json={}
    ).json()
    assert cases["total_cases"] == 1
    assert cases["cases"][0]["variant"] == ["A", "B"]
