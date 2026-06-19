import io

from tests.conftest import register

SAMPLE_CSV = (
    "case,activity,time\n"
    "1,Register,2023-01-01 08:00:00\n"
    "1,Review,2023-01-01 09:30:00\n"
)


def _import_log(client, name="L"):
    up = client.post(
        "/api/logs/upload",
        files={"file": ("log.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")},
    ).json()["upload_id"]
    resp = client.post(
        "/api/logs/import",
        json={
            "upload_id": up,
            "name": name,
            "mapping": {"case_id": "case", "activity": "activity", "timestamp": "time"},
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["log_id"]


def test_register_and_me(client):
    token = register(client, "a@example.com")
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "a@example.com"
    assert resp.json()["workspace_id"]


def test_register_duplicate_email(client):
    register(client, "dup@example.com")
    resp = client.post(
        "/api/auth/register",
        json={"email": "dup@example.com", "password": "password123"},
    )
    assert resp.status_code == 409


def test_login_success_and_failure(client):
    register(client, "login@example.com", "password123")
    ok = client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": "password123"},
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    bad = client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": "wrong"},
    )
    assert bad.status_code == 401


def test_me_requires_valid_token(client):
    assert client.get("/api/auth/me").status_code in (401, 403)
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401


def test_idor_cross_workspace_isolation(client):
    """User B must not read or delete User A's log."""
    token_a = register(client, "tenant-a@example.com")
    token_b = register(client, "tenant-b@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    client.headers.update(headers_a)
    log_id = _import_log(client, "A's log")

    # A sees their own log.
    assert client.get(f"/api/logs/{log_id}").status_code == 200

    # B is isolated: cannot see A's log in their list...
    client.headers.update(headers_b)
    assert client.get("/api/logs").json() == []
    # ...gets 404 (not 403) so IDs can't be probed across tenants...
    assert client.get(f"/api/logs/{log_id}").status_code == 404
    # ...and cannot delete it.
    assert client.delete(f"/api/logs/{log_id}").status_code == 404

    # A's log is untouched.
    client.headers.update(headers_a)
    assert client.get(f"/api/logs/{log_id}").status_code == 200
