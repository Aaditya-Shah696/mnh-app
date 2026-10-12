"""Recommender tests run against the REAL local embedding model."""
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import login, make_record_payload


def _seed(client, patient, diagnosis, complaints, drug):
    payload = make_record_payload(
        patient["id"], diagnosis=diagnosis, history=complaints,
    )
    payload["treatment_items"] = [
        {"category": "discharge", "drug": drug, "dose": "1", "route": "PO",
         "frequency": "OD", "duration": "5 days"},
    ]
    return client.post("/api/records", json=payload).json()["id"]


def test_semantic_match_beats_wording(client, patient):
    gastro = _seed(client, patient, "Acute gastroenteritis",
                   "Loose stools and vomiting since yesterday", "ORS sachet")
    chest = _seed(client, patient, "Lower respiratory tract infection",
                  "Cough with sputum and fever", "Tab Amoxicillin")
    uti = _seed(client, patient, "Urinary tract infection",
                "Burning micturition and fever", "Tab Nitrofurantoin")

    # Held-out phrasing, no shared keywords with the gastro record text
    resp = client.post("/api/match", json={
        "text": "frequent watery motions, dehydrated, vomited twice", "limit": 3,
    })
    assert resp.status_code == 200
    results = resp.json()
    assert results, "no matches returned"
    assert results[0]["record"]["id"] == gastro
    assert results[0]["score"] > results[-1]["score"]

    for rid in (gastro, chest, uti):
        client.delete(f"/api/records/{rid}")


def test_exclude_record_id(client, patient):
    rid = _seed(client, patient, "Dengue fever", "High fever and body ache", "Paracetamol")
    resp = client.post("/api/match", json={
        "text": "dengue fever high fever body ache",
        "limit": 5,
        "exclude_record_id": rid,
    })
    assert all(r["record"]["id"] != rid for r in resp.json())
    client.delete(f"/api/records/{rid}")


def test_empty_text_rejected(client):
    assert client.post("/api/match", json={"text": ""}).status_code == 422


def test_limit_bounds(client):
    assert client.post("/api/match", json={"text": "fever", "limit": 0}).status_code == 422
    assert client.post("/api/match", json={"text": "fever", "limit": 21}).status_code == 422


def _second_user_client(client, username):
    created = client.post("/api/users", json={
        "username": username, "display_name": username.title(), "role": "staff",
        "password": "match-viewer-password-1",
    })
    assert created.status_code == 201, created.text
    viewer = TestClient(app, base_url="https://testserver")
    login(viewer, {"username": username, "password": "match-viewer-password-1"})
    return viewer, created.json()["id"]


def _match_view_rows(client, user_id):
    rows = client.get("/api/audit", params={
        "action": "record.view", "user_id": user_id, "limit": 500,
    }).json()["items"]
    return [r for r in rows if r["detail"] == {"via": "similar_cases"}]


def test_match_returns_only_panel_fields(client, patient):
    rid = _seed(client, patient, "Febrile seizure", "Fever with a brief generalised fit", "Syp Paracetamol")
    results = client.post("/api/match", json={"text": "fever with a fit", "limit": 5}).json()
    record = next(r["record"] for r in results if r["record"]["id"] == rid)
    assert set(record) == {
        "id", "patient_id", "patient_name", "admission_date", "discharge_date",
        "diagnosis", "advice", "treatment_items",
    }
    assert record["patient_name"] == patient["name"]
    assert record["treatment_items"] and all(
        t["category"] == "discharge" for t in record["treatment_items"]
    )
    client.delete(f"/api/records/{rid}")


def test_every_record_shown_by_match_is_audited_once_per_window(client, patient):
    rid = _seed(client, patient, "Bronchiolitis", "Wheeze and cough in an infant", "Nebulised salbutamol")
    viewer, viewer_id = _second_user_client(client, "match-viewer")

    first = viewer.post("/api/match", json={"text": "infant with wheeze and cough", "limit": 3})
    assert first.status_code == 200
    shown = [r["record"]["id"] for r in first.json()]
    assert rid in shown
    rows = _match_view_rows(client, viewer_id)
    assert sorted(r["entity_id"] for r in rows) == sorted(shown)
    assert all(r["entity_type"] == "record" and r["username"] == "match-viewer" for r in rows)

    again = viewer.post("/api/match", json={"text": "infant with wheeze and cough", "limit": 3})
    assert [r["record"]["id"] for r in again.json()] == shown
    assert len(_match_view_rows(client, viewer_id)) == len(shown)

    client.delete(f"/api/records/{rid}")
