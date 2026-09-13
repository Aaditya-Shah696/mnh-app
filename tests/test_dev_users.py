"""scripts/dev_users.py: creates the fixed dev accounts, never in production."""
import pytest

from app import config
from app.database import SessionLocal
from scripts import dev_users


def test_dev_users_created_and_can_login(anon_client):
    db = SessionLocal()
    try:
        touched = dev_users.ensure_dev_users(db)
    finally:
        db.close()
    assert touched == ["mitesh", "reception"]
    for username, _, role, password in dev_users.DEV_USERS:
        resp = anon_client.post("/api/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == role
        anon_client.post("/api/auth/logout")


def test_dev_users_idempotent_and_resets(anon_client):
    db = SessionLocal()
    try:
        dev_users.ensure_dev_users(db)
        from app import models
        u = db.query(models.User).filter_by(username="mitesh").one()
        u.password_hash = "broken"
        u.is_active = False
        u.failed_logins = 9
        db.commit()
        dev_users.ensure_dev_users(db)
    finally:
        db.close()
    resp = anon_client.post("/api/auth/login", json={"username": "mitesh", "password": "dev-admin-password-1"})
    assert resp.status_code == 200


def test_dev_users_refused_in_production(monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    db = SessionLocal()
    try:
        with pytest.raises(RuntimeError, match="production"):
            dev_users.ensure_dev_users(db)
    finally:
        db.close()
