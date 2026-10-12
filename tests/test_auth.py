"""Login, sessions, cookies, lockout, throttling, password change."""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app import auth, config, models
from app import main as main_module
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
    cleared = _cookie_header(resp).lower()
    assert config.SESSION_COOKIE_NAME in cleared
    assert "max-age=0" in cleared
    assert "path=/" in cleared and "secure" in cleared and "httponly" in cleared
    assert config.SESSION_COOKIE_NAME not in client.cookies
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


def _bad_login(client, username=STAFF["username"], password="wrong-password-xx"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _failure_row(username, ip="testclient"):
    db = SessionLocal()
    try:
        return db.get(models.LoginFailure, (username, ip))
    finally:
        db.close()


def test_account_lockout_after_repeated_failures(anon_client):
    for _ in range(config.LOGIN_LOCK_THRESHOLD):
        assert _bad_login(anon_client).status_code == 401
    locked = _bad_login(anon_client, password=STAFF["password"])
    assert locked.status_code == 429
    assert "Too many failed sign-in attempts" in locked.json()["detail"]
    assert int(locked.headers["retry-after"]) > 0
    row = _failure_row(STAFF["username"])
    assert row.failures == config.LOGIN_LOCK_THRESHOLD
    assert row.locked_until > models.utcnow()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter_by(username=STAFF["username"]).one()
        assert user.locked_until is not None and user.locked_until > models.utcnow()
        assert user.failed_logins == config.LOGIN_LOCK_THRESHOLD
    finally:
        db.close()
    admin = TestClient(app, base_url="https://testserver", client=("10.9.9.9", 50000))
    login(admin, ADMIN)
    resp = admin.patch(f"/api/users/{user.id}", json={"unlock": True})
    assert resp.status_code == 200
    assert resp.json()["locked_until"] is None and resp.json()["failed_logins"] == 0
    assert _failure_row(STAFF["username"]) is None
    assert anon_client.post("/api/auth/login", json={
        "username": STAFF["username"], "password": STAFF["password"],
    }).status_code == 200


def test_parallel_wrong_passwords_cannot_bypass_lockout():
    attempts = 20

    def attempt(_):
        client = TestClient(app, base_url="https://testserver")
        return _bad_login(client).status_code

    with ThreadPoolExecutor(max_workers=attempts) as pool:
        statuses = list(pool.map(attempt, range(attempts)))

    assert statuses.count(401) == config.LOGIN_LOCK_THRESHOLD
    assert statuses.count(429) == attempts - config.LOGIN_LOCK_THRESHOLD
    row = _failure_row(STAFF["username"])
    assert row.failures == config.LOGIN_LOCK_THRESHOLD
    assert row.locked_until > models.utcnow()
    fresh = TestClient(app, base_url="https://testserver")
    assert _bad_login(fresh, password=STAFF["password"]).status_code == 429


def test_lockout_only_blocks_the_guessing_address():
    attacker = TestClient(app, base_url="https://testserver", client=("198.51.100.7", 40000))
    for _ in range(config.LOGIN_LOCK_THRESHOLD + 3):
        _bad_login(attacker, username=ADMIN["username"])
    assert _bad_login(attacker, username=ADMIN["username"],
                      password=ADMIN["password"]).status_code == 429
    clinic = TestClient(app, base_url="https://testserver", client=("203.0.113.20", 40000))
    assert clinic.post("/api/auth/login", json={
        "username": ADMIN["username"], "password": ADMIN["password"],
    }).status_code == 200
    assert _bad_login(attacker, username=ADMIN["username"],
                      password=ADMIN["password"]).status_code == 429


def test_unknown_username_locks_out_exactly_like_a_real_one(anon_client):
    responses = {}
    for name in (STAFF["username"], "nobody-at-all"):
        for _ in range(config.LOGIN_LOCK_THRESHOLD):
            assert _bad_login(anon_client, username=name).status_code == 401
        responses[name] = _bad_login(anon_client, username=name)
    real, ghost = responses[STAFF["username"]], responses["nobody-at-all"]
    assert real.status_code == ghost.status_code == 429
    assert real.json() == ghost.json()


def test_lockout_duration_doubles():
    threshold = config.LOGIN_LOCK_THRESHOLD
    base = config.LOGIN_LOCK_BASE_MINUTES
    assert auth.lock_minutes(threshold - 1) == 0
    assert auth.lock_minutes(threshold) == base
    assert auth.lock_minutes(threshold + 1) == 2 * base
    assert auth.lock_minutes(threshold + 2) == 4 * base
    assert auth.lock_minutes(threshold + 500) == config.LOGIN_LOCK_MAX_HOURS * 60


def test_stale_failure_counters_are_pruned(anon_client):
    _bad_login(anon_client)
    db = SessionLocal()
    try:
        row = db.get(models.LoginFailure, (STAFF["username"], "testclient"))
        row.last_failure_at = models.utcnow() - timedelta(hours=config.LOGIN_FAILURE_RESET_HOURS + 1)
        db.commit()
        assert auth.prune_login_failures(db) == 1
        db.commit()
    finally:
        db.close()
    assert _failure_row(STAFF["username"]) is None


def test_wrong_current_password_counts_toward_lockout(staff_client):
    for _ in range(config.LOGIN_LOCK_THRESHOLD):
        wrong = staff_client.post("/api/auth/password", json={
            "current_password": "not-current-password", "new_password": "a-long-new-password-1",
        })
        assert wrong.status_code == 403
    blocked = staff_client.post("/api/auth/password", json={
        "current_password": STAFF["password"], "new_password": "a-long-new-password-1",
    })
    assert blocked.status_code == 429
    assert _bad_login(staff_client, password=STAFF["password"]).status_code == 429


def test_rejected_logins_are_logged_for_fail2ban(caplog):
    client = TestClient(app, base_url="https://testserver", client=("192.0.2.44", 40000))
    with caplog.at_level(logging.WARNING, logger="mnh.security"):
        _bad_login(client, username="nobody-for-f2b")
        _bad_login(client)
        client.post("/api/auth/login", json={
            "username": STAFF["username"], "password": STAFF["password"],
        })
    records = [r for r in caplog.records if r.name == "mnh.security"]
    assert [r.getMessage() for r in records] == ["login rejected from 192.0.2.44"] * 2
    assert all(r.levelname == "WARNING" for r in records)


def test_rejected_login_log_never_carries_untrusted_text(caplog):
    with caplog.at_level(logging.WARNING, logger="mnh.security"):
        auth.log_rejected_login("1.2.3.4 login rejected from 5.6.7.8")
        auth.log_rejected_login("testclient")
        auth.log_rejected_login(None)
        auth.log_rejected_login("2001:db8::1")
    lines = [r.getMessage() for r in caplog.records if r.name == "mnh.security"]
    assert lines == ["login rejected from 2001:db8::1"]


def test_fail2ban_fixture_matches_the_app_log_format():
    fixture = Path(__file__).parent / "fixtures" / "fail2ban" / "mnh-login.match.log"
    record = logging.LogRecord("mnh.security", logging.WARNING, __file__, 0,
                               "login rejected from %s", ("203.0.113.9",), None)
    message = logging.Formatter(main_module.LOG_FORMAT).format(record)
    lines = fixture.read_text(encoding="utf-8").splitlines()
    assert any(line.endswith(": " + message) for line in lines)


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
