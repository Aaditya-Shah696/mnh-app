from tests.conftest import make_record_payload


def test_create_and_fetch_patient(client):
    resp = client.post("/api/patients", json={
        "name": "Anandi Bhagat", "sex": "F", "dob": "1975-01-30",
        "phone": "9800000010", "address": "Somewhere",
    })
    assert resp.status_code == 201
    got = client.get(f"/api/patients/{resp.json()['id']}").json()
    assert got["name"] == "Anandi Bhagat"
    assert got["dob"] == "1975-01-30"


def test_blank_name_rejected(client):
    assert client.post("/api/patients", json={"name": "   "}).status_code == 422


def test_invalid_sex_rejected(client):
    assert client.post("/api/patients", json={"name": "X", "sex": "Q"}).status_code == 422


def test_search_by_name_and_phone(client):
    client.post("/api/patients", json={"name": "Searchable Soman", "phone": "9333311111"})
    by_name = client.get("/api/patients", params={"q": "searchable"}).json()
    assert any(p["name"] == "Searchable Soman" for p in by_name)
    by_phone = client.get("/api/patients", params={"q": "93333"}).json()
    assert any(p["name"] == "Searchable Soman" for p in by_phone)


def test_update_patient(client, patient):
    patient["phone"] = "9111100000"
    resp = client.put(f"/api/patients/{patient['id']}", json={
        "name": patient["name"], "phone": "9111100000",
    })
    assert resp.status_code == 200
    assert resp.json()["phone"] == "9111100000"


def test_delete_guard_with_records(client, patient):
    record = client.post("/api/records", json=make_record_payload(patient["id"]))
    assert record.status_code == 201
    assert client.delete(f"/api/patients/{patient['id']}").status_code == 409
    assert client.delete(f"/api/records/{record.json()['id']}").status_code == 204
    assert client.delete(f"/api/patients/{patient['id']}").status_code == 204


def test_missing_patient_404(client):
    assert client.get("/api/patients/999999").status_code == 404
