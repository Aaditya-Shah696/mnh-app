"""Audit trail: every mutation writes exactly one row inside the transaction,
views and PDFs are logged, values are never logged, and the table is
append-only at the database level."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app import config, models
from app.database import SessionLocal
from tests.conftest import ADMIN, STAFF, login, make_record_payload


def _rows(client, **params):
    resp = client.get("/api/audit", params=params)
    assert resp.status_code == 200
    return resp.json()


def _count(client, **params):
    return _rows(client, limit=1, **params)["total"]


def test_login_events_are_logged(anon_client, client):
    before = _count(client, action="login.failure", username="nobody-zz")
    anon_client.post("/api/auth/login", json={"username": "nobody-zz", "password": "wrong-wrong-1"})
    after = _rows(client, action="login.failure", username="nobody-zz", limit=1)
    assert after["total"] == before + 1
    row = after["items"][0]
    assert row["user_id"] is None and row["username"] == "nobody-zz"
    assert row["detail"] == {"reason": "unknown_user"}
    assert "wrong-wrong-1" not in str(after)

    success = _rows(client, action="login.success", username=ADMIN["username"], limit=1)
    assert success["total"] >= 1 and success["items"][0]["user_id"] is not None


def test_record_lifecycle_is_audited(client, patient):
    me = client.get("/api/auth/me").json()
    payload = make_record_payload(patient["id"], status="draft")
    rid = client.post("/api/records", json=payload).json()["id"]

    created = _rows(client, action="record.create", entity_type="record", entity_id=rid)
    assert created["total"] == 1
    assert created["items"][0]["user_id"] == me["id"]
    assert created["items"][0]["detail"]["status"] == "draft"

    client.get(f"/api/records/{rid}")
    assert _count(client, action="record.view", entity_id=rid) == 1

    update = make_record_payload(patient["id"], status="final", diagnosis="Changed dx")
    del update["patient_id"]
    client.put(f"/api/records/{rid}", json=update)
    upd = _rows(client, action="record.update", entity_id=rid)
    assert upd["total"] == 1
    fields = upd["items"][0]["detail"]["fields"]
    assert "diagnosis" in fields and "status" in fields
    assert "Changed dx" not in upd["items"][0]["detail"].__repr__()
    assert _count(client, action="record.finalize", entity_id=rid) == 1

    client.get(f"/api/records/{rid}/pdf")
    assert _count(client, action="record.pdf", entity_id=rid) == 1

    client.delete(f"/api/records/{rid}")
    assert _count(client, action="record.delete", entity_id=rid) == 1
    client.post(f"/api/records/{rid}/restore")
    assert _count(client, action="record.restore", entity_id=rid) == 1
    client.delete(f"/api/records/{rid}")


def test_patient_lifecycle_is_audited(client):
    pid = client.post("/api/patients", json={"name": "Audited Patient"}).json()["id"]
    assert _count(client, action="patient.create", entity_id=pid) == 1
    client.get(f"/api/patients/{pid}")
    assert _count(client, action="patient.view", entity_id=pid) == 1
    client.put(f"/api/patients/{pid}", json={"name": "Audited Patient", "sex": "M"})
    upd = _rows(client, action="patient.update", entity_id=pid)
    assert upd["items"][0]["detail"]["fields"] == ["sex"]


def test_staff_actions_are_attributed_to_staff(staff_client, client):
    pid = staff_client.post("/api/patients", json={"name": "Staff Made"}).json()["id"]
    row = _rows(client, action="patient.create", entity_id=pid)["items"][0]
    assert row["username"] == STAFF["username"]


def test_backup_and_user_actions_are_audited(client):
    client.post("/api/backup")
    assert _count(client, action="backup.create") >= 1
    u = client.post("/api/users", json={
        "username": "audited_user", "display_name": "A", "role": "staff",
        "password": "a-fine-password-123",
    }).json()
    assert _count(client, action="user.create", entity_id=u["id"]) == 1
    client.patch(f"/api/users/{u['id']}", json={"is_active": False})
    assert _count(client, action="user.deactivate", entity_id=u["id"]) == 1


def test_filters_and_paging(client):
    page = _rows(client, limit=2, offset=0)
    assert len(page["items"]) <= 2 and page["limit"] == 2
    prefix = _rows(client, action="login.", limit=5)
    assert all(r["action"].startswith("login.") for r in prefix["items"])
    since = _rows(client, since="2999-01-01T00:00:00", limit=5)
    assert since["total"] == 0
    actions = client.get("/api/audit/actions").json()
    assert "record.view" in actions["actions"]


def test_audit_row_is_in_same_transaction_as_change(client, patient, monkeypatch):
    """If the commit fails, neither the record nor its audit row exists."""
    from app.routers import records as records_router

    def boom(*args, **kwargs):
        raise RuntimeError("embedding exploded")

    monkeypatch.setattr(records_router.embeddings, "refresh_record_vectors", boom)
    before = _count(client, action="record.create")
    with pytest.raises(RuntimeError):
        client.post("/api/records", json=make_record_payload(patient["id"]))
    assert _count(client, action="record.create") == before


def test_audit_log_is_append_only_at_db_level():
    db = SessionLocal()
    try:
        row = models.AuditLog(action="logout", username="trigger-test")
        db.add(row)
        db.commit()
        rid = row.id
    finally:
        db.close()
    con = sqlite3.connect(config.DB_PATH)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            con.execute("UPDATE audit_log SET action='login.success' WHERE id=?", (rid,))
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            con.execute("DELETE FROM audit_log WHERE id=?", (rid,))
    finally:
        con.close()
    db = SessionLocal()
    try:
        assert db.execute(text("SELECT action FROM audit_log WHERE id=:i"), {"i": rid}).scalar() == "logout"
    finally:
        db.close()


def test_unknown_action_is_a_programming_error():
    from app.audit import audit

    with pytest.raises(ValueError):
        audit(None, "record.explode")


def test_prefix_filter_includes_the_bare_action(anon_client, client):
    login(anon_client, STAFF)
    assert anon_client.post("/api/auth/logout").status_code == 204
    rows = _rows(client, action="logout.", limit=50)
    assert rows["total"] >= 1
    assert all(r["action"] == "logout" or r["action"].startswith("logout.") for r in rows["items"])
    login_rows = _rows(client, action="login.", limit=50)
    assert login_rows["total"] >= 1
    assert all(r["action"].startswith("login.") for r in login_rows["items"])


def test_date_filters_honour_the_timezone_offset(client):
    pid = client.post("/api/patients", json={"name": "Timezone Probe"}).json()["id"]
    row = _rows(client, action="patient.create", entity_id=pid)["items"][0]
    ts = datetime.fromisoformat(row["ts"])
    ist = timezone(timedelta(hours=5, minutes=30))
    local = ts.replace(tzinfo=timezone.utc).astimezone(ist)
    just_before = (local - timedelta(seconds=1)).isoformat()
    just_after = (local + timedelta(seconds=1)).isoformat()
    assert _count(client, action="patient.create", entity_id=pid, since=just_before) == 1
    assert _count(client, action="patient.create", entity_id=pid, since=just_after) == 0
    assert _count(client, action="patient.create", entity_id=pid, until=just_after) == 1
    assert _count(client, action="patient.create", entity_id=pid, until=just_before) == 0


def test_keyset_paging_never_duplicates_or_skips_while_events_arrive(client):
    for n in range(7):
        client.post("/api/patients", json={"name": f"Paging Probe {n}"})
    snapshot = [r["id"] for r in _rows(client, action="patient.create", limit=500)["items"]]

    first = _rows(client, action="patient.create", limit=3)
    assert [r["id"] for r in first["items"]] == snapshot[:3]
    assert first["next_before_id"] == snapshot[2]

    for n in range(2):
        client.post("/api/patients", json={"name": f"Arrived Mid Paging {n}"})

    second = _rows(client, action="patient.create", limit=3, before_id=first["next_before_id"])
    assert [r["id"] for r in second["items"]] == snapshot[3:6]

    last = _rows(client, action="patient.create", limit=500, before_id=snapshot[-1] + 1)
    assert last["next_before_id"] is None
