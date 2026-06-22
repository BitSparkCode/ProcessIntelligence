import io

# A->B->C in case 1; A->C in case 2.
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


def test_inductive_miner_graph(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(f"/api/discovery/{log_id}/inductive-miner")
    assert resp.status_code == 200, resp.text
    graph = resp.json()

    assert graph["algorithm"] == "inductive"
    assert {n["label"] for n in graph["nodes"]} == {"A", "B", "C"}
    assert graph["case_count"] == 2
    assert graph["start_activities"] == ["A"]
    assert graph["end_activities"] == ["C"]

    edges = {(e["source"], e["target"]) for e in graph["edges"]}
    # The sound model connects A->B->C and the A->C skip.
    assert ("A", "B") in edges
    assert ("B", "C") in edges


def test_bpmn_export_is_valid_xml(auth_client):
    import xml.etree.ElementTree as ET

    log_id = _import(auth_client)
    resp = auth_client.get(f"/api/discovery/{log_id}/bpmn")
    assert resp.status_code == 200, resp.text
    assert "application/xml" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]

    root = ET.fromstring(resp.text)
    assert root.tag.endswith("definitions")
    # All three tasks are present as <task name="..."> elements.
    names = {
        el.get("name")
        for el in root.iter()
        if el.tag.endswith("}task") or el.tag.endswith("task")
    }
    assert {"A", "B", "C"} <= names


def test_bpmn_export_has_laid_out_diagram(auth_client):
    """Shapes must have real, distinct coordinates so modelers don't stack them."""
    import xml.etree.ElementTree as ET

    log_id = _import(auth_client)
    resp = auth_client.get(f"/api/discovery/{log_id}/bpmn")
    assert resp.status_code == 200, resp.text

    root = ET.fromstring(resp.text)
    bounds = [el for el in root.iter() if el.tag.endswith("}Bounds")]
    assert bounds, "export contains no BPMNDI bounds"

    positions = {(b.get("x"), b.get("y")) for b in bounds}
    # A broken (un-laid-out) export puts every shape at the same 0,0 origin.
    assert positions != {("0", "0")}
    assert len(positions) > 1, "all shapes share one position (overlapping pile)"
    # Width/height must be non-zero so shapes are actually visible.
    assert all(float(b.get("width")) > 0 and float(b.get("height")) > 0 for b in bounds)

    waypoints = [el for el in root.iter() if el.tag.endswith("}waypoint")]
    assert waypoints, "export contains no edge waypoints"
    assert {(w.get("x"), w.get("y")) for w in waypoints} != {("0", "0")}


def test_inductive_requires_owned_log(client):
    from tests.conftest import register

    token_a = register(client, "ia@example.com")
    token_b = register(client, "ib@example.com")
    client.headers.update({"Authorization": f"Bearer {token_a}"})
    log_id = _import(client)

    client.headers.update({"Authorization": f"Bearer {token_b}"})
    assert client.post(f"/api/discovery/{log_id}/inductive-miner").status_code == 404
    assert client.get(f"/api/discovery/{log_id}/bpmn").status_code == 404
