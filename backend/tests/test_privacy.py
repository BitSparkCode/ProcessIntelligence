import io

from sqlalchemy import func, select

from app.models import Activity, Attribute, Case, Event, EventLog, Resource

PRIVACY_CSV = (
    "case,activity,time,who\n"
    "1,A,2023-01-01 08:00:00,bob\n"
    "1,B,2023-01-01 09:00:00,sue\n"
    "2,A,2023-01-02 08:00:00,bob\n"
    "2,C,2023-01-02 08:30:00,sue\n"
)


def _import(client) -> str:
    up = client.post(
        "/api/logs/upload",
        files={"file": ("d.csv", io.BytesIO(PRIVACY_CSV.encode()), "text/csv")},
    ).json()["upload_id"]
    return client.post(
        "/api/logs/import",
        json={
            "upload_id": up,
            "name": "to-delete",
            "mapping": {
                "case_id": "case",
                "activity": "activity",
                "timestamp": "time",
                "resource": "who",
            },
        },
    ).json()["log_id"]


def _counts(db) -> dict[str, int]:
    return {
        m.__name__: db.scalar(select(func.count()).select_from(m))
        for m in (EventLog, Case, Event, Activity, Resource, Attribute)
    }


def test_delete_log_removes_all_derived_data(auth_client, db_session):
    log_id = _import(auth_client)

    before = _counts(db_session)
    assert before["Event"] == 4
    assert before["Case"] == 2
    assert before["Resource"] == 2

    resp = auth_client.delete(f"/api/logs/{log_id}")
    assert resp.status_code == 204, resp.text

    after = _counts(db_session)
    # Right-to-erasure: nothing derived from the log may survive its deletion.
    assert all(count == 0 for count in after.values()), after


def test_cannot_delete_another_tenants_log(client):
    from tests.conftest import register

    token_a = register(client, "da@example.com")
    token_b = register(client, "db@example.com")
    client.headers.update({"Authorization": f"Bearer {token_a}"})
    log_id = _import(client)

    client.headers.update({"Authorization": f"Bearer {token_b}"})
    assert client.delete(f"/api/logs/{log_id}").status_code == 404

    # Owner can still delete it -> isolation didn't break ownership.
    client.headers.update({"Authorization": f"Bearer {token_a}"})
    assert client.delete(f"/api/logs/{log_id}").status_code == 204
