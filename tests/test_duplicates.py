"""Duplicate-entry warning before a new record is saved (REAL embedding model)."""
from tests.conftest import make_record_payload

DX = dict(
    diagnosis="Acute bacterial meningitis",
    history="High fever, neck stiffness and two seizures since this morning",
    course_in_hospital="IV ceftriaxone and vancomycin for 10 days",
)


def _patient(client, name):
    return client.post("/api/patients", json={"name": name}).json()


def _check(client, patient_id, **fields):
    resp = client.post("/api/records/duplicate-check",
                       json=make_record_payload(patient_id, **fields))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _candidate_ids(result):
    return [c["record"]["id"] for c in result["candidates"]]


def test_same_admission_day_is_flagged(client):
    p = _patient(client, "Duplicate Same Day")
    existing = client.post("/api/records", json=make_record_payload(
        p["id"], admission_date="2026-08-01T09:00:00", diagnosis="Bronchiolitis")).json()
    result = _check(client, p["id"], admission_date="2026-08-01T21:30:00",
                    diagnosis="Completely different wording")
    [candidate] = result["candidates"]
    assert candidate["record"]["id"] == existing["id"]
    assert candidate["reasons"] == ["same_admission_date"]


def test_near_identical_content_within_the_window_is_flagged(client):
    p = _patient(client, "Duplicate Near Identical")
    existing = client.post("/api/records", json=make_record_payload(
        p["id"], admission_date="2026-08-01T09:00:00", **DX)).json()
    result = _check(client, p["id"], admission_date="2026-08-03T09:00:00", **DX)
    [candidate] = result["candidates"]
    assert candidate["record"]["id"] == existing["id"]
    assert candidate["reasons"] == ["near_identical"]
    assert candidate["similarity"] > 0.97


def test_same_content_long_apart_is_a_readmission_not_a_duplicate(client):
    p = _patient(client, "Duplicate Readmission")
    client.post("/api/records", json=make_record_payload(
        p["id"], admission_date="2026-01-01T09:00:00", **DX))
    assert _check(client, p["id"], admission_date="2026-08-01T09:00:00", **DX)["candidates"] == []


def test_both_reasons_together(client):
    p = _patient(client, "Duplicate Both")
    client.post("/api/records", json=make_record_payload(
        p["id"], admission_date="2026-08-01T09:00:00", **DX))
    [candidate] = _check(client, p["id"], admission_date="2026-08-01T09:00:00", **DX)["candidates"]
    assert candidate["reasons"] == ["same_admission_date", "near_identical"]


def test_other_patients_deleted_records_and_itself_are_ignored(client):
    p = _patient(client, "Duplicate Scope")
    other = _patient(client, "Duplicate Scope Other")
    client.post("/api/records", json=make_record_payload(
        other["id"], admission_date="2026-08-01T09:00:00", **DX))
    gone = client.post("/api/records", json=make_record_payload(
        p["id"], admission_date="2026-08-01T09:00:00", **DX)).json()
    client.delete(f"/api/records/{gone['id']}")
    assert _check(client, p["id"], admission_date="2026-08-01T09:00:00", **DX)["candidates"] == []

    itself = client.post("/api/records", json=make_record_payload(
        p["id"], admission_date="2026-08-01T09:00:00", **DX)).json()
    resp = client.post("/api/records/duplicate-check", json={
        **make_record_payload(p["id"], admission_date="2026-08-01T09:00:00", **DX),
        "record_id": itself["id"],
    })
    assert resp.json()["candidates"] == []


def test_unknown_patient_is_404(client):
    resp = client.post("/api/records/duplicate-check", json=make_record_payload(9_999_999))
    assert resp.status_code == 404
