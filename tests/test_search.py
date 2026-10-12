from app.querying import contains_pattern, escape_like
from tests.conftest import make_record_payload


def test_escape_like():
    assert escape_like("100%") == "100\\%"
    assert escape_like("a_b") == "a\\_b"
    assert escape_like("back\\slash") == "back\\\\slash"
    assert contains_pattern("x%") == "%x\\%%"


def test_patient_and_record_search_treat_wildcards_literally(client):
    percent = client.post("/api/patients", json={"name": "Percent 100% Kumar"}).json()
    underscore = client.post("/api/patients", json={"name": "Under_score Shah"}).json()
    plain = client.post("/api/patients", json={"name": "Plain Wildcard Probe"}).json()
    record = client.post("/api/records", json=make_record_payload(percent["id"])).json()

    by_percent = {p["id"] for p in client.get("/api/patients", params={"q": "%"}).json()}
    assert percent["id"] in by_percent
    assert not by_percent & {underscore["id"], plain["id"]}

    by_underscore = {p["id"] for p in client.get("/api/patients", params={"q": "_"}).json()}
    assert underscore["id"] in by_underscore
    assert not by_underscore & {percent["id"], plain["id"]}

    records = client.get("/api/records", params={"q": "100%"}).json()
    assert [r["id"] for r in records] == [record["id"]]
    assert client.get("/api/records", params={"q": "_score"}).json() == []

    for patient in (percent, underscore, plain):
        client.delete(f"/api/patients/{patient['id']}")
