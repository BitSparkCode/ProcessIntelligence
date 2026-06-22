import io
import warnings

import pandas as pd
import pm4py

# Two cases follow A,B,C; one case skips B (A,C).
CONFORMANCE_CSV = (
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
        files={"file": ("d.csv", io.BytesIO(CONFORMANCE_CSV.encode()), "text/csv")},
    ).json()["upload_id"]
    return client.post(
        "/api/logs/import",
        json={
            "upload_id": up,
            "name": "conformance",
            "mapping": {"case_id": "case", "activity": "activity", "timestamp": "time"},
        },
    ).json()["log_id"]


def _strict_abc_bpmn() -> bytes:
    """A reference model that requires A -> B -> C in strict order."""
    warnings.filterwarnings("ignore")
    df = pd.DataFrame(
        [
            {
                "case:concept:name": "m",
                "concept:name": act,
                "time:timestamp": pd.Timestamp(f"2024-01-01T1{i}:00:00Z"),
            }
            for i, act in enumerate(["A", "B", "C"])
        ]
    )
    net, im, fm = pm4py.discover_petri_net_inductive(df)
    bpmn = pm4py.convert_to_bpmn(net, im, fm)
    from pm4py.objects.bpmn.exporter.variants import etree as bpmn_etree

    xml = bpmn_etree.get_xml_string(bpmn)
    return xml if isinstance(xml, bytes) else xml.encode()


def test_conformance_flags_missing_activity(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/analysis/{log_id}/conformance",
        files={"bpmn": ("soll.bpmn", io.BytesIO(_strict_abc_bpmn()), "application/xml")},
        data={"method": "alignment"},
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()

    assert report["case_count"] == 3
    # Two A,B,C cases conform; the A,C case deviates (B missing).
    assert report["fitting_case_count"] == 2
    assert 0.0 < report["fitness"] <= 1.0

    summary = {(d["kind"], d["activity"]): d for d in report["deviation_summary"]}
    assert ("missing", "B") in summary
    assert summary[("missing", "B")]["case_count"] == 1

    bad = [c for c in report["case_deviations"] if not c["is_fitting"]]
    assert len(bad) == 1
    assert bad[0]["case_key"] == "3"
    assert any("B" in d for d in bad[0]["deviations"])


def test_conformance_with_explanation(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/analysis/{log_id}/conformance",
        files={"bpmn": ("soll.bpmn", io.BytesIO(_strict_abc_bpmn()), "application/xml")},
        data={"method": "alignment", "explain": "true"},
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()
    # AI disabled in CI -> deterministic heuristic explanation.
    assert report["explanation_source"] == "heuristic"
    assert report["explanation"]
    assert "fitness" in report["explanation"].lower() or "conform" in report["explanation"].lower()


def test_conformance_rejects_non_bpmn(auth_client):
    log_id = _import(auth_client)
    resp = auth_client.post(
        f"/api/analysis/{log_id}/conformance",
        files={"bpmn": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 400


def test_conformance_requires_owned_log(client):
    from tests.conftest import register

    token_a = register(client, "ca@example.com")
    token_b = register(client, "cb@example.com")
    client.headers.update({"Authorization": f"Bearer {token_a}"})
    log_id = _import(client)

    client.headers.update({"Authorization": f"Bearer {token_b}"})
    resp = client.post(
        f"/api/analysis/{log_id}/conformance",
        files={"bpmn": ("soll.bpmn", io.BytesIO(_strict_abc_bpmn()), "application/xml")},
    )
    assert resp.status_code == 404
