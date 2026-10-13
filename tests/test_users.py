"""Admin user management and the last-admin guards."""
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import login


def _new_user(client, username, role="staff", password="a-fine-password-123"):
    resp = client.post("/api/users", json={
        "username": username, "display_name": username.title(), "role": role,
        "password": password,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_list_and_duplicate(client):
    u = _new_user(client, "nurse1")
    assert u["role"] == "staff" and u["is_active"] is True
    names = [x["username"] for x in client.get("/api/users").json()]
    assert "nurse1" in names and "admin" in names
    dup = client.post("/api/users", json={
        "username": "NURSE1", "display_name": "x", "role": "staff",
        "password": "a-fine-password-123",
    })
    assert dup.status_code == 409


def test_username_validation(client):
    bad = client.post("/api/users", json={
        "username": "bad name!", "display_name": "x", "role": "staff",
        "password": "a-fine-password-123",
    })
    assert bad.status_code == 422
    weak = client.post("/api/users", json={
        "username": "weakpw", "display_name": "x", "role": "staff", "password": "short",
    })
    assert weak.status_code == 422
    role = client.post("/api/users", json={
        "username": "roleuser", "display_name": "x", "role": "superuser",
        "password": "a-fine-password-123",
    })
    assert role.status_code == 422


def test_update_display_name_and_role(client):
    u = _new_user(client, "promote")
    resp = client.patch(f"/api/users/{u['id']}", json={
        "display_name": "Dr. Promoted", "role": "admin",
    })
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Dr. Promoted"
    assert resp.json()["role"] == "admin"
    # A freshly promoted admin can use admin routes
    other = TestClient(app, base_url="https://testserver")
    login(other, {"username": "promote", "password": "a-fine-password-123"})
    assert other.get("/api/users").status_code == 200
    # demote again so later guards are testable
    assert client.patch(f"/api/users/{u['id']}", json={"role": "staff"}).status_code == 200
    assert other.get("/api/users").status_code == 403


def test_cannot_change_own_role_or_deactivate_self(client):
    me = client.get("/api/auth/me").json()
    assert client.patch(f"/api/users/{me['id']}", json={"role": "staff"}).status_code == 409
    assert client.patch(f"/api/users/{me['id']}", json={"is_active": False}).status_code == 409


def test_last_admin_guard(client):
    """Promote a second admin, then try to demote the first via the second:
    allowed. Then try to demote the last remaining admin: refused."""
    second = _new_user(client, "second_admin", role="admin")
    me = client.get("/api/auth/me").json()

    other = TestClient(app, base_url="https://testserver")
    login(other, {"username": "second_admin", "password": "a-fine-password-123"})
    # Two active admins exist: demoting one is fine.
    assert other.patch(f"/api/users/{me['id']}", json={"role": "staff"}).status_code == 200
    # Now second_admin is the only admin: nobody can demote or deactivate them.
    assert client.patch(f"/api/users/{second['id']}", json={"role": "staff"}).status_code == 403
    assert other.patch(f"/api/users/{second['id']}", json={"role": "staff"}).status_code == 409
    # Restore the fixture admin.
    assert other.patch(f"/api/users/{me['id']}", json={"role": "admin"}).status_code == 200
    assert other.patch(f"/api/users/{second['id']}", json={"is_active": False}).status_code == 409
    assert client.patch(f"/api/users/{second['id']}", json={"is_active": False}).status_code == 200


def test_reset_password_revokes_sessions(client):
    u = _new_user(client, "resetme")
    victim = TestClient(app, base_url="https://testserver")
    login(victim, {"username": "resetme", "password": "a-fine-password-123"})
    assert victim.get("/api/auth/me").status_code == 200
    assert client.post(f"/api/users/{u['id']}/reset-password",
                       json={"new_password": "short"}).status_code == 422
    assert client.post(f"/api/users/{u['id']}/reset-password",
                       json={"new_password": "brand-new-password-456"}).status_code == 204
    assert victim.get("/api/auth/me").status_code == 401
    login(victim, {"username": "resetme", "password": "brand-new-password-456"})


def test_missing_user_404(client):
    assert client.patch("/api/users/999999", json={"unlock": True}).status_code == 404


def test_staff_sees_403_not_users(staff_client):
    assert staff_client.get("/api/users").status_code == 403
