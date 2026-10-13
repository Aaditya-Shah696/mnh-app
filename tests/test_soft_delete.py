"""Soft delete: rows stay, are hidden everywhere, and can be restored."""
from app import models
from app.database import SessionLocal
from tests.conftest import make_record_payload


def test_deleted_record_hidden_from_get_list_pdf_and_match(client, patient):
    payload = make_record_payload(
        patient["id"], diagnosis="Scrub typhus with eschar", history="Fever, eschar on thigh",
    )
    rid = client.post("/api/records", json=payload).json()["id"]
    assert client.delete(f"/api/records/{rid}").status_code == 204

    assert client.get(f"/api/records/{rid}").status_code == 404
    assert client.get(f"/api/records/{rid}/pdf").status_code == 404
    assert client.put(f"/api/records/{rid}", json=make_record_payload(patient["id"])).status_code == 404
    assert all(r["id"] != rid for r in client.get("/api/records").json())
    assert all(r["id"] != rid for r in client.get(f"/api/patients/{patient['id']}/records").json())
    match = client.post("/api/match", json={"text": "scrub typhus eschar fever thigh", "limit": 5})
    assert match.status_code == 200
    assert all(m["record"]["id"] != rid for m in match.json())

    # The row is still in the database with its vectors.
    db = SessionLocal()
    try:
        row = db.get(models.DischargeRecord, rid)
        assert row is not None and row.deleted_at is not None and row.vectors
    finally:
        db.close()

    # Admin can see it in the deleted list and open it explicitly.
    deleted = client.get("/api/records", params={"deleted": "true"}).json()
    assert any(r["id"] == rid and r["deleted_at"] for r in deleted)
    assert client.get(f"/api/records/{rid}", params={"include_deleted": "true"}).status_code == 200

    restored = client.post(f"/api/records/{rid}/restore")
    assert restored.status_code == 200 and restored.json()["deleted_at"] is None
    assert client.get(f"/api/records/{rid}").status_code == 200
    assert client.post(f"/api/records/{rid}/restore").status_code == 409
    client.delete(f"/api/records/{rid}")


def test_staff_cannot_delete_or_see_deleted(staff_client, client, patient):
    rid = client.post("/api/records", json=make_record_payload(patient["id"])).json()["id"]
    assert staff_client.delete(f"/api/records/{rid}").status_code == 403
    assert staff_client.get("/api/records", params={"deleted": "true"}).status_code == 403
    assert staff_client.get(f"/api/records/{rid}", params={"include_deleted": "true"}).status_code == 403
    assert staff_client.get("/api/patients", params={"deleted": "true"}).status_code == 403
    client.delete(f"/api/records/{rid}")


def test_delete_patient_cascades_and_restore_brings_records_back(client):
    pid = client.post("/api/patients", json={"name": "Cascade Kid"}).json()["id"]
    r1 = client.post("/api/records", json=make_record_payload(pid)).json()["id"]
    r2 = client.post("/api/records", json=make_record_payload(pid, diagnosis="Second visit")).json()["id"]
    # One record deleted earlier, on its own, must NOT come back with the patient.
    r0 = client.post("/api/records", json=make_record_payload(pid, diagnosis="Old mistake")).json()["id"]
    assert client.delete(f"/api/records/{r0}").status_code == 204

    assert client.delete(f"/api/patients/{pid}").status_code == 204
    assert client.get(f"/api/patients/{pid}").status_code == 404
    assert client.get(f"/api/records/{r1}").status_code == 404
    assert client.get(f"/api/records/{r2}").status_code == 404
    assert all(p["id"] != pid for p in client.get("/api/patients", params={"q": "Cascade"}).json())
    assert any(p["id"] == pid for p in client.get("/api/patients", params={"deleted": "true"}).json())
    # Its records are listed for the admin with include_deleted
    listed = client.get(f"/api/patients/{pid}/records", params={"include_deleted": "true"}).json()
    assert {r["id"] for r in listed} == {r0, r1, r2}

    restored = client.post(f"/api/patients/{pid}/restore")
    assert restored.status_code == 200 and restored.json()["deleted_at"] is None
    assert client.get(f"/api/records/{r1}").status_code == 200
    assert client.get(f"/api/records/{r2}").status_code == 200
    assert client.get(f"/api/records/{r0}").status_code == 404  # stayed deleted
    assert client.post(f"/api/patients/{pid}/restore").status_code == 409


def test_restoring_record_of_deleted_patient_restores_patient(client):
    pid = client.post("/api/patients", json={"name": "Orphan Guard"}).json()["id"]
    rid = client.post("/api/records", json=make_record_payload(pid)).json()["id"]
    client.delete(f"/api/patients/{pid}")
    resp = client.post(f"/api/records/{rid}/restore")
    assert resp.status_code == 200
    assert resp.json()["patient"]["deleted_at"] is None
    assert client.get(f"/api/patients/{pid}").status_code == 200


def test_hard_delete_is_gone(client, patient):
    """No API path removes a row: delete then look in the DB."""
    rid = client.post("/api/records", json=make_record_payload(patient["id"])).json()["id"]
    client.delete(f"/api/records/{rid}")
    db = SessionLocal()
    try:
        assert db.get(models.DischargeRecord, rid) is not None
        assert len(db.get(models.DischargeRecord, rid).treatment_items) == 2
    finally:
        db.close()


def test_new_record_carries_author(client, patient):
    me = client.get("/api/auth/me").json()
    rec = client.post("/api/records", json=make_record_payload(patient["id"])).json()
    assert rec["created_by"] == me["id"] and rec["updated_by"] == me["id"]
    client.delete(f"/api/records/{rec['id']}")
