"""Recommender tests run against the REAL local embedding model."""
from tests.conftest import make_record_payload


def _seed(client, patient, diagnosis, complaints, drug):
    payload = make_record_payload(
        patient["id"], diagnosis=diagnosis, presenting_complaints=complaints,
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
