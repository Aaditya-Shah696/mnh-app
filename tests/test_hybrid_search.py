"""One search box: keyword (FTS5) plus meaning (REAL local embedding model)."""
from sqlalchemy import text

from app import models
from app.database import SessionLocal
from app.services import search
from tests.conftest import make_record_payload


def _new_patient(client, name):
    return client.post("/api/patients", json={"name": name}).json()


def _record(client, patient, **overrides):
    return client.post("/api/records", json=make_record_payload(patient["id"], **overrides)).json()


def _search(client, q, **params):
    resp = client.get("/api/search", params={"q": q, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ids(result, keyword=None):
    return [h["record"]["id"] for h in result["hits"]
            if keyword is None or h["keyword"] is keyword]


# ---------- Pure pieces ----------

def test_match_expression_neutralises_fts_syntax():
    assert search.match_expression('ceftri axone', None) == '"ceftri"* AND "axone"*'
    assert search.match_expression('" OR NEAR( * -x', None) == '"OR"* AND "NEAR"* AND "x"*'
    assert search.match_expression("  ", None) is None
    assert search.match_expression("fever", ("course",)) == '{course} : ("fever"*)'
    many = search.match_expression(" ".join(f"w{i}" for i in range(30)), None)
    assert many.count("AND") == search.MAX_QUERY_TOKENS - 1


def test_segments_split_highlights():
    marked = f"Inj {search.HIT_START}Ceftriaxone{search.HIT_END} 1 g IV"
    assert search.segments(marked) == [
        {"text": "Inj ", "hit": False}, {"text": "Ceftriaxone", "hit": True},
        {"text": " 1 g IV", "hit": False},
    ]
    assert search.segments("plain") == [{"text": "plain", "hit": False}]


def test_meaning_outliers_needs_a_standout_and_a_corpus():
    flat = [(i, 0.60, "summary") for i in range(30)]
    assert search.meaning_outliers(flat) == []
    standout = [(99, 0.82, "summary")] + [(i, 0.55 + (i % 5) * 0.01, "summary") for i in range(30)]
    assert search.meaning_outliers(standout) == [(99, 0.82)]
    too_few = [(99, 0.9, "summary"), (1, 0.5, "summary")]
    assert search.meaning_outliers(too_few) == []
    low = [(99, 0.50, "summary")] + [(i, 0.30, "summary") for i in range(30)]
    assert search.meaning_outliers(low) == []  # stands out but below the floor


# ---------- Keyword search through the API ----------

def test_drug_found_with_section_and_highlight(client):
    p = _new_patient(client, "Keyword Probe One")
    rec = _record(client, p, treatment_items=[
        {"category": "hospital", "drug": "Inj Piperacillin-tazobactam", "dose": "100 mg/kg",
         "route": "IV", "frequency": "8 hourly", "duration": "5 days"},
    ])
    hit = next(h for h in _search(client, "piperacillin")["hits"] if h["record"]["id"] == rec["id"])
    assert hit["keyword"] is True
    assert hit["section"] == "medicines"
    marked = [s["text"] for s in hit["snippet"] if s["hit"]]
    assert marked and marked[0].lower().startswith("piperacillin")


def test_prefix_and_stemming(client):
    p = _new_patient(client, "Stemming Probe")
    rec = _record(client, p, diagnosis="Complex febrile seizures with postictal drowsiness")
    assert rec["id"] in _ids(_search(client, "seizure"))       # stem: seizures -> seizur
    assert rec["id"] in _ids(_search(client, "postict"))       # typed prefix
    assert rec["id"] in _ids(_search(client, "Seizures drows"))  # case-insensitive, all words
    assert rec["id"] not in _ids(_search(client, "seizure zzqqxx"), keyword=True)  # every word must match


def test_section_filter_limits_where_words_count(client):
    p = _new_patient(client, "Section Probe")
    rec = _record(client, p, course_in_hospital="Developed thrombophlebitis at the cannula site on day 3")
    assert rec["id"] in _ids(_search(client, "thrombophlebitis", section="course"), keyword=True)
    # The word only counts in the section searched. (A meaning-only hit can
    # still appear under its own heading: on a tiny corpus of short
    # investigation texts the least-unrelated one can stand out.)
    assert rec["id"] not in _ids(_search(client, "thrombophlebitis", section="investigations"), keyword=True)
    assert client.get("/api/search", params={"q": "x", "section": "bogus"}).status_code == 422


def test_patient_name_search_and_rename(client):
    p = _new_patient(client, "Zorawar Renamecheck")
    rec = _record(client, p)
    hit = next(h for h in _search(client, "Zorawar")["hits"] if h["record"]["id"] == rec["id"])
    assert hit["section"] == "patient_name"
    client.put(f"/api/patients/{p['id']}", json={"name": "Yuvan Renamecheck"})
    assert rec["id"] in _ids(_search(client, "Yuvan"))
    assert rec["id"] not in _ids(_search(client, "Zorawar"))


def test_deleted_records_never_appear(client):
    p = _new_patient(client, "Deleted Search Probe")
    rec = _record(client, p, diagnosis="Kerosene ingestion with aspiration pneumonitis")
    assert rec["id"] in _ids(_search(client, "kerosene"))
    client.delete(f"/api/records/{rec['id']}")
    assert rec["id"] not in _ids(_search(client, "kerosene"))
    assert rec["id"] not in _ids(_search(client, "kerosene ingestion aspiration"))
    client.post(f"/api/records/{rec['id']}/restore")
    assert rec["id"] in _ids(_search(client, "kerosene"))


def test_hostile_queries_do_not_error(client):
    for q in ['"', "AND", "NEAR(", "*", "a OR b", "{course}: x", "') ; DROP TABLE x; --", "ñandú"]:
        assert client.get("/api/search", params={"q": q}).status_code == 200, q


def test_search_is_audited_without_the_query(client):
    p = _new_patient(client, "Audit Search Probe")
    rec = _record(client, p, diagnosis="Organophosphate poisoning")
    _search(client, "organophosphate")
    row = client.get("/api/audit", params={"action": "record.search"}).json()["items"][0]
    assert rec["id"] in row["detail"]["results"]
    assert row["detail"]["section"] == "any"
    assert "organophosphate" not in str(row["detail"]).lower()


def test_staff_can_search(staff_client):
    assert staff_client.get("/api/search", params={"q": "fever"}).status_code == 200


# ---------- Meaning ----------

# A varied paediatric corpus, so whether a record "stands out" does not
# depend on what earlier tests happened to leave in the shared database.
BACKGROUND = [
    ("Acute gastroenteritis with some dehydration", "Loose stools and vomiting for two days"),
    ("Community acquired pneumonia", "Cough, fever and fast breathing for four days"),
    ("Dengue fever with thrombocytopenia", "High fever, body ache, platelets 40,000"),
    ("Simple febrile seizure", "One generalised convulsion with fever"),
    ("Urinary tract infection", "Fever and crying while passing urine"),
    ("Acute exacerbation of asthma", "Wheeze and breathlessness since night"),
    ("Typhoid fever", "Step-ladder fever for a week, Widal positive"),
    ("Iron deficiency anaemia", "Pallor and tiredness, haemoglobin 6.2"),
    ("Cellulitis of the right leg", "Red, hot, swollen leg for three days"),
    ("Bronchiolitis", "Infant with cough, coryza and chest retractions"),
    ("Diabetic ketoacidosis", "Vomiting, deep breathing, blood sugar 480"),
    ("Acute otitis media", "Ear pain and fever since yesterday"),
]


def _seed_background(client):
    p = _new_patient(client, "Meaning Background")
    for dx, hx in BACKGROUND:
        _record(client, p, diagnosis=dx, history=hx, treatment_items=[])


def test_meaning_finds_a_record_with_no_shared_words(client):
    _seed_background(client)
    p = _new_patient(client, "Meaning Probe")
    rec = _record(client, p, diagnosis="Snake bite, viper envenomation",
                  history="Bitten on the ankle in a field, swelling and bleeding from the wound",
                  treatment_items=[{"category": "hospital", "drug": "Anti snake venom",
                                    "dose": "10 vials", "route": "IV", "frequency": "stat",
                                    "duration": "1 day"}])
    result = _search(client, "venomous serpent attacked leg")
    assert result["semantic_used"] is True
    hit = next(h for h in result["hits"] if h["record"]["id"] == rec["id"])
    assert hit["keyword"] is False and hit["similarity"] > 0.6
    # Meaning-only hits come after every word match.
    flags = [h["keyword"] for h in result["hits"]]
    assert flags == sorted(flags, reverse=True)


def test_unrelated_query_returns_no_meaning_hits(client):
    _seed_background(client)
    result = _search(client, "quarterly invoice spreadsheet formatting")
    assert [h for h in result["hits"] if not h["keyword"]] == []


def test_short_queries_are_word_only(client):
    assert _search(client, "abc")["semantic_used"] is False


# ---------- Keeping the index in step ----------

def test_sync_repairs_missing_changed_and_orphan_rows(client):
    p = _new_patient(client, "Sync Probe")
    rec = _record(client, p, diagnosis="Hand foot and mouth disease")
    db = SessionLocal()
    try:
        assert search.sync(db) == {"indexed": 0, "removed": 0}  # routes kept it in step

        db.execute(text("DELETE FROM record_search WHERE rowid = :id"), {"id": rec["id"]})
        row = db.get(models.DischargeRecord, rec["id"])
        row.diagnosis = "Herpangina"  # written outside the API, as a script would
        db.execute(text("INSERT INTO record_search (rowid, content_hash) VALUES (987654321, 'x')"))
        db.commit()

        assert search.sync(db) == {"indexed": 1, "removed": 1}
    finally:
        db.close()
    assert rec["id"] in _ids(_search(client, "herpangina"))
