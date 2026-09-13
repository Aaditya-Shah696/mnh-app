from tests.conftest import make_record_payload


def test_create_and_fetch_patient(client):
    resp = client.post("/api/patients", json={
        "name": "Anandi Bhagat", "sex": "F", "dob": "1975-01-30",
        "chronic_conditions": "Type 2 diabetes",
        "past_history": "Cataract surgery 2020",
    })
    assert resp.status_code == 201
    got = client.get(f"/api/patients/{resp.json()['id']}").json()
    assert got["name"] == "Anandi Bhagat"
    assert got["dob"] == "1975-01-30"
    assert got["chronic_conditions"] == "Type 2 diabetes"
    assert got["past_history"] == "Cataract surgery 2020"
    assert "phone" not in got
    assert "address" not in got


def test_blank_name_rejected(client):
    assert client.post("/api/patients", json={"name": "   "}).status_code == 422


def test_invalid_sex_rejected(client):
    assert client.post("/api/patients", json={"name": "X", "sex": "Q"}).status_code == 422


def test_search_is_name_only(client):
    client.post("/api/patients", json={"name": "Searchable Soman"})
    by_name = client.get("/api/patients", params={"q": "searchable"}).json()
    assert any(p["name"] == "Searchable Soman" for p in by_name)
    # Phone was removed: a phone-like query must not match anything for them
    by_number = client.get("/api/patients", params={"q": "93333"}).json()
    assert not any(p["name"] == "Searchable Soman" for p in by_number)


def test_update_patient(client, patient):
    resp = client.put(f"/api/patients/{patient['id']}", json={
        "name": patient["name"],
        "chronic_conditions": "Hypothyroidism, prediabetes",
    })
    assert resp.status_code == 200
    assert resp.json()["chronic_conditions"] == "Hypothyroidism, prediabetes"


def test_persistent_fields_available_for_prefill(client, patient):
    """The editor prefills chronic conditions / past history from the
    patient carried on the record; both fetch paths must supply them."""
    rid = client.post("/api/records", json=make_record_payload(patient["id"])).json()["id"]
    record = client.get(f"/api/records/{rid}").json()
    assert record["patient"]["chronic_conditions"] == "Hypothyroidism"
    assert record["patient"]["past_history"] == "LSCS 2018"
    direct = client.get(f"/api/patients/{patient['id']}").json()
    assert direct["chronic_conditions"] == "Hypothyroidism"
    client.delete(f"/api/records/{rid}")


def test_write_back_updates_profile(client, patient):
    """Saving a discharge writes edited chronic conditions back to the
    profile (the UI PUTs the patient); later reads see the new values."""
    resp = client.put(f"/api/patients/{patient['id']}", json={
        "name": patient["name"], "sex": patient["sex"], "dob": patient["dob"],
        "chronic_conditions": "Hypothyroidism, new-onset hypertension",
        "past_history": patient["past_history"],
    })
    assert resp.status_code == 200
    rid = client.post("/api/records", json=make_record_payload(patient["id"])).json()["id"]
    record = client.get(f"/api/records/{rid}").json()
    assert record["patient"]["chronic_conditions"] == "Hypothyroidism, new-onset hypertension"
    client.delete(f"/api/records/{rid}")


def test_delete_patient_soft_deletes_records_too(client, patient):
    record = client.post("/api/records", json=make_record_payload(patient["id"]))
    assert record.status_code == 201
    assert client.delete(f"/api/patients/{patient['id']}").status_code == 204
    assert client.get(f"/api/records/{record.json()['id']}").status_code == 404
    assert client.get(f"/api/patients/{patient['id']}").status_code == 404
    assert client.post(f"/api/patients/{patient['id']}/restore").status_code == 200
    assert client.get(f"/api/records/{record.json()['id']}").status_code == 200


def test_missing_patient_404(client):
    assert client.get("/api/patients/999999").status_code == 404
