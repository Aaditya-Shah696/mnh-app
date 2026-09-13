"""Login, sessions, cookies, lockout, throttling, password change."""
from datetime import timedelta

from fastapi.testclient import TestClient

from app import auth, config, models
from app.database import SessionLocal
from app.main import app
from tests.conftest import ADMIN, STAFF, login


def _cookie_header(resp) -> str:
    return resp.headers.get("set-cookie", "")


def test_login_sets_hardened_cookie(anon_client):
    resp = anon_client.post("/api/auth/login", json={
        "username": ADMIN["username"], "password": ADMIN["password"],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "admin" and body["role"] == "admin"
    assert "password_hash" not in body
    cookie = _cookie_header(resp).lower()
    assert config.SESSION_COOKIE_NAME in cookie
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=strict" in cookie
    assert "path=/" in cookie
    # The cookie value is the raw token; only its hash is stored.
    raw = resp.cookies[config.SESSION_COOKIE_NAME]
    db = SessionLocal()
    try:
        assert db.query(models.UserSession).filter_by(token_hash=raw).first() is None
        assert db.query(models.UserSession).filter_by(
            token_hash=auth._token_hash(raw)).first() is not None
    finally:
        db.close()


def test_username_is_case_insensitive(anon_client):
    resp = anon_client.post("/api/auth/login", json={
        "username": "  ADMIN ", "password": ADMIN["password"],
    })
    assert resp.status_code == 200


def test_me_requires_session(anon_client):
    assert anon_client.get("/api/auth/me").status_code == 401


def test_me_after_login(client):
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["display_name"] == ADMIN["display_name"]


def test_wrong_password_and_unknown_user_look_identical(anon_client):
    bad = anon_client.post("/api/auth/login", json={
        "username": ADMIN["username"], "password": "definitely-wrong-password",
    })
    unknown = anon_client.post("/api/auth/login", json={
        "username": "nobody-here", "password": "definitely-wrong-password",
    })
    assert bad.status_code == unknown.status_code == 401
    assert bad.json()["detail"] == unknown.json()["detail"] == auth.LOGIN_FAILED_DETAIL


def test_logout_revokes_session(client):
    assert client.get("/api/auth/me").status_code == 200
    raw = client.cookies[config.SESSION_COOKIE_NAME]
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    # Replaying the old token after logout must fail too.
    replay = TestClient(app, base_url="https://testserver")
    replay.cookies.set(config.SESSION_COOKIE_NAME, raw)
    assert replay.get("/api/auth/me").status_code == 401


def test_garbage_cookie_is_401(anon_client):
    anon_client.cookies.set(config.SESSION_COOKIE_NAME, "not-a-real-token")
    assert anon_client.get("/api/auth/me").status_code == 401


def test_idle_and_absolute_expiry(client):
    raw = client.cookies[config.SESSION_COOKIE_NAME]
    db = SessionLocal()
    try:
        session = db.query(models.UserSession).filter_by(token_hash=auth._token_hash(raw)).one()
        session.last_seen_at = models.utcnow() - timedelta(hours=config.SESSION_IDLE_HOURS + 1)
        db.commit()
    finally:
        db.close()
    assert client.get("/api/auth/me").status_code == 401

    login(client, ADMIN)
    raw = client.cookies[config.SESSION_COOKIE_NAME]
    db = SessionLocal()
    try:
        session = db.query(models.UserSession).filter_by(token_hash=auth._token_hash(raw)).one()
        session.expires_at = models.utcnow() - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()
    assert client.get("/api/auth/me").status_code == 401


def test_account_lockout_after_repeated_failures(anon_client):
    for _ in range(config.LOGIN_LOCK_THRESHOLD):
        r = anon_client.post("/api/auth/login", json={
            "username": STAFF["username"], "password": "wrong-password-xx",
        })
        assert r.status_code == 401
    # Correct password is now refused because the account is locked...
    locked = anon_client.post("/api/auth/login", json={
        "username": STAFF["username"], "password": STAFF["password"],
    })
    assert locked.status_code == 401
    assert locked.json()["detail"] == auth.LOGIN_FAILED_DETAIL
    db = SessionLocal()
    try:
        user = db.query(models.User).filter_by(username=STAFF["username"]).one()
        assert user.locked_until is not None and user.locked_until > models.utcnow()
        assert user.failed_logins == config.LOGIN_LOCK_THRESHOLD
    finally:
        db.close()
    # ...until an admin unlocks it.
    admin = TestClient(app, base_url="https://testserver")
    login(admin, ADMIN)
    resp = admin.patch(f"/api/users/{user.id}", json={"unlock": True})
    assert resp.status_code == 200
    assert resp.json()["locked_until"] is None and resp.json()["failed_logins"] == 0
    assert anon_client.post("/api/auth/login", json={
        "username": STAFF["username"], "password": STAFF["password"],
    }).status_code == 200


def test_lockout_duration_doubles(monkeypatch):
    user = models.User(username="x", display_name="x", password_hash="h", role="staff")
    user.failed_logins = config.LOGIN_LOCK_THRESHOLD - 1
    auth.register_login_failure(user)
    first = user.locked_until - models.utcnow()
    auth.register_login_failure(user)
    second = user.locked_until - models.utcnow()
    assert timedelta(minutes=config.LOGIN_LOCK_BASE_MINUTES - 1) < first
    assert second > first * 1.8
    for _ in range(20):
        auth.register_login_failure(user)
    assert user.locked_until - models.utcnow() <= timedelta(hours=config.LOGIN_LOCK_MAX_HOURS)


def test_per_ip_throttle(anon_client, monkeypatch):
    monkeypatch.setattr(auth.login_ip_throttle, "limit", 3)
    auth.login_ip_throttle.reset()
    for _ in range(3):
        anon_client.post("/api/auth/login", json={"username": "zzz", "password": "nope-nope-nope"})
    r = anon_client.post("/api/auth/login", json={"username": "zzz", "password": "nope-nope-nope"})
    assert r.status_code == 429
    assert r.headers.get("retry-after")


def test_inactive_user_cannot_login_and_live_session_dies(anon_client):
    admin = TestClient(app, base_url="https://testserver")
    login(admin, ADMIN)
    created = admin.post("/api/users", json={
        "username": "leaver", "display_name": "Leaver", "role": "staff",
        "password": "leaver-password-123",
    })
    assert created.status_code == 201, created.text
    uid = created.json()["id"]
    login(anon_client, {"username": "leaver", "password": "leaver-password-123"})
    assert anon_client.get("/api/auth/me").status_code == 200
    assert admin.patch(f"/api/users/{uid}", json={"is_active": False}).status_code == 200
    assert anon_client.get("/api/auth/me").status_code == 401
    assert anon_client.post("/api/auth/login", json={
        "username": "leaver", "password": "leaver-password-123",
    }).status_code == 401


def test_change_password_revokes_other_sessions(staff_client):
    other = TestClient(app, base_url="https://testserver")
    login(other, STAFF)
    assert other.get("/api/auth/me").status_code == 200

    weak = staff_client.post("/api/auth/password", json={
        "current_password": STAFF["password"], "new_password": "short",
    })
    assert weak.status_code == 422
    wrong = staff_client.post("/api/auth/password", json={
        "current_password": "not-current-password", "new_password": "a-long-new-password-1",
    })
    assert wrong.status_code == 403

    ok = staff_client.post("/api/auth/password", json={
        "current_password": STAFF["password"], "new_password": "a-long-new-password-1",
    })
    assert ok.status_code == 204
    assert staff_client.get("/api/auth/me").status_code == 200  # current session kept
    assert other.get("/api/auth/me").status_code == 401           # others revoked
    assert staff_client.post("/api/auth/login", json={
        "username": STAFF["username"], "password": "a-long-new-password-1",
    }).status_code == 200
    # put it back for the other tests
    assert staff_client.post("/api/auth/password", json={
        "current_password": "a-long-new-password-1", "new_password": STAFF["password"],
    }).status_code == 204


def test_password_policy():
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        auth.validate_new_password("tooshort", "u")
    with pytest.raises(HTTPException):
        auth.validate_new_password("x" * 300, "u")
    with pytest.raises(HTTPException):
        auth.validate_new_password("reception-desk", "Reception-Desk")
    auth.validate_new_password("correct horse battery", "u")


def test_hash_roundtrip_and_rehash():
    h = auth.hash_password("some-password-here")
    assert h.startswith("$argon2id$")
    assert auth.verify_password(h, "some-password-here")
    assert not auth.verify_password(h, "some-password-herE")
    assert not auth.verify_password("garbage", "x")
    assert not auth.password_needs_rehash(h)
    assert auth.password_needs_rehash("garbage")
