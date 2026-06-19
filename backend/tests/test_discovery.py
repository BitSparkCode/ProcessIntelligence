import io

# A->B->C in case 1; A->C in case 2. So A>B=1, B>C=1, A>C=1.
DISC_CSV = (
    "case,activity,time\n"
    "1,A,2023-01-01 08:00:00\n"
    "1,B,2023-01-01 09:00:00\n"
    "1,C,2023-01-01 10:00:00\n"
    "2,A,2023-01-02 08:00:00\n"
    "2,C,2023-01-02 08:30:00\n"
)


def _import(client) -> str:
    up = client.post(
        "/api/logs/upload",
        files={"file": ("d.csv", io.BytesIO(DISC_CSV.encode()), "text/csv")},
    ).json()["upload_id"]
    return client.post(
        "/api/logs/import",
        json={
            "upload_id": up,
            "name": "disc",
            "mapping": {"case_id": "case", "activity": "activity", "timestamp": "time"},
        },
    ).json()["log_id"]


def test_heuristic_miner_graph(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/discovery/{log_id}/heuristic-miner",
        json={"dependency_threshold": 0.0, "frequency_threshold": 1},
    )
    assert resp.status_code == 200, resp.text
    graph = resp.json()

    labels = {n["label"] for n in graph["nodes"]}
    assert labels == {"A", "B", "C"}
    assert graph["case_count"] == 2
    assert graph["start_activities"] == ["A"]
    assert sorted(graph["end_activities"]) == ["C"]

    edges = {(e["source"], e["target"]): e for e in graph["edges"]}
    assert ("A", "B") in edges
    assert ("B", "C") in edges
    assert ("A", "C") in edges
    # A->B average duration is one hour (3600s).
    assert edges[("A", "B")]["avg_duration_seconds"] == 3600.0


def test_frequency_threshold_prunes_edges(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/discovery/{log_id}/heuristic-miner",
        json={"dependency_threshold": 0.0, "frequency_threshold": 2},
    )
    assert resp.status_code == 200
    # No directly-follows pair occurs twice, so all edges are pruned.
    assert resp.json()["edges"] == []


def test_discovery_requires_owned_log(client):
    from tests.conftest import register

    token_a = register(client, "da@example.com")
    token_b = register(client, "db@example.com")
    client.headers.update({"Authorization": f"Bearer {token_a}"})
    log_id = _import(client)

    client.headers.update({"Authorization": f"Bearer {token_b}"})
    resp = client.post(f"/api/discovery/{log_id}/heuristic-miner", json={})
    assert resp.status_code == 404
