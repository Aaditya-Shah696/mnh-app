from tests.conftest import make_record_payload


def test_full_round_trip(client, patient):
    payload = make_record_payload(patient["id"])
    created = client.post("/api/records", json=payload)
    assert created.status_code == 201
    rid = created.json()["id"]

    fetched = client.get(f"/api/records/{rid}").json()
    for key, sent in payload.items():
        if key in ("patient_id", "treatment_items"):
            continue
        assert str(fetched[key]) == str(sent), key
    assert [t["drug"] for t in fetched["treatment_items"]] == ["IV RL", "ORS sachet"]
    assert fetched["patient"]["id"] == patient["id"]

    client.delete(f"/api/records/{rid}")


def test_update_replaces_treatment_items(client, patient):
    created = client.post("/api/records", json=make_record_payload(patient["id"]))
    rid = created.json()["id"]
    update = make_record_payload(patient["id"])
    del update["patient_id"]
    update["treatment_items"] = [
        {"category": "discharge", "drug": "Tab Paracetamol", "dose": "650 mg",
         "route": "PO", "frequency": "TDS", "duration": "3 days"},
    ]
    resp = client.put(f"/api/records/{rid}", json=update)
    assert resp.status_code == 200
    items = resp.json()["treatment_items"]
    assert len(items) == 1 and items[0]["drug"] == "Tab Paracetamol"
    client.delete(f"/api/records/{rid}")


def test_record_requires_existing_patient(client):
    assert client.post(
        "/api/records", json=make_record_payload(999999)
    ).status_code == 404


def test_invalid_status_rejected(client, patient):
    payload = make_record_payload(patient["id"], status="bogus")
    assert client.post("/api/records", json=payload).status_code == 422


def test_delete_cascades_treatment_items(client, patient):
    created = client.post("/api/records", json=make_record_payload(patient["id"]))
    rid = created.json()["id"]
    assert client.delete(f"/api/records/{rid}").status_code == 204
    assert client.get(f"/api/records/{rid}").status_code == 404


def test_list_filter_by_patient_name(client, patient):
    created = client.post("/api/records", json=make_record_payload(patient["id"]))
    rid = created.json()["id"]
    hits = client.get("/api/records", params={"q": "Test Patient"}).json()
    assert any(r["id"] == rid for r in hits)
    misses = client.get("/api/records", params={"q": "zzz-nobody"}).json()
    assert all(r["id"] != rid for r in misses)
    client.delete(f"/api/records/{rid}")


def test_embedding_stored_on_save(client, patient):
    from app import models
    from app.database import SessionLocal

    created = client.post("/api/records", json=make_record_payload(patient["id"]))
    rid = created.json()["id"]
    db = SessionLocal()
    try:
        row = db.get(models.DischargeRecord, rid)
        assert row.embedding is not None
        assert len(row.embedding) % 4 == 0 and len(row.embedding) >= 4 * 128
        assert row.embedding_model
    finally:
        db.close()
    client.delete(f"/api/records/{rid}")
