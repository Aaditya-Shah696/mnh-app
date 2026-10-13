"""ICD-10-CM codes: the CMS file builder, the code list, suggestions (REAL
local embedding model, over the test subset in tests/fixtures), and codes
stored on records."""
import importlib.util
import time
from pathlib import Path

import numpy as np
import pytest

from app import config
from app.database import SessionLocal
from app.services import codes
from tests.conftest import make_record_payload

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("build_icd10cm", ROOT / "scripts" / "build_icd10cm.py")
build_icd10cm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_icd10cm)


def _order_line(n: int, code: str, billable: bool, desc: str) -> str:
    return f"{n:05d} {code:<7} {'1' if billable else '0'} {desc[:60]:<60} {desc}"


@pytest.fixture(scope="module")
def ready_index():
    codes.start_build_thread()  # no-op if the app already started it
    deadline = time.monotonic() + 120
    while codes.index.state != "ready" and time.monotonic() < deadline:
        assert codes.index.state != "failed", codes.index.error
        time.sleep(0.1)
    assert codes.index.state == "ready"
    return codes.index


# ---------- Building the code file from CMS's formats ----------

def test_order_file_parsing_and_filter():
    text = "\n".join([
        _order_line(1, "A01", False, "Typhoid and paratyphoid fevers"),
        _order_line(2, "A0100", True, "Typhoid fever, unspecified"),
        _order_line(3, "S72001A", True, "Fracture of unsp part of neck of right femur, init"),
        _order_line(4, "S72001D", True, "Fracture of unsp part of neck of right femur, subs"),
        _order_line(5, "W010XXA", True, "Fall on same level from slipping, initial encounter"),
        _order_line(6, "QA00", True, "A new-style code with a letter second"),
    ])
    rows = build_icd10cm.parse_order_file(text)
    assert rows[1] == ("A0100", True, "Typhoid fever, unspecified")
    kept = [c for c, billable, _ in rows if build_icd10cm.keep(c, billable)]
    assert kept == ["A0100", "S72001A", "QA00"]
    assert build_icd10cm.dotted("A0100") == "A01.00" and build_icd10cm.dotted("A09") == "A09"
    with pytest.raises(ValueError, match="CMS order-file layout"):
        build_icd10cm.parse_order_file("garbage line")


INDEX_XML = b"""<ICD10CM.index><letter><title>F</title>
<mainTerm><title>Fever <nemod>(inanition)</nemod></title><code>R50.9</code>
  <term level="1"><title>enteric</title><code>A01.00</code></term>
  <term level="1"><title>with</title>
    <term level="2"><title>convulsions</title><code>R56.00</code></term></term>
  <term level="1"><title>rheumatic</title><see>Rheumatic fever</see></term>
</mainTerm></letter></ICD10CM.index>"""

TABULAR_XML = b"""<ICD10CM.tabular><chapter><section><diag><name>B08.4</name>
<desc>Enteroviral vesicular stomatitis with exanthem</desc>
<inclusionTerm><note>Hand, foot and mouth disease</note></inclusionTerm>
</diag></section></chapter></ICD10CM.tabular>"""


def test_index_and_inclusion_extraction():
    assert build_icd10cm.index_phrases(INDEX_XML) == [
        ("Fever", "R50.9"), ("Fever, enteric", "A01.00"), ("Fever, with, convulsions", "R56.00"),
    ]
    assert build_icd10cm.inclusion_terms(TABULAR_XML) == [("Hand, foot and mouth disease", "B08.4")]


def test_build_merges_and_dedupes():
    order = "\n".join([
        _order_line(1, "A0100", True, "Typhoid fever, unspecified"),
        _order_line(2, "B084", True, "Enteroviral vesicular stomatitis with exanthem"),
        _order_line(3, "R509", True, "Fever, unspecified"),
    ])
    rows = build_icd10cm.build(order, INDEX_XML, TABULAR_XML)
    assert ("A01.00", "title", "Typhoid fever, unspecified") in rows
    assert ("A01.00", "index", "Fever, enteric") in rows
    assert ("B08.4", "inclusion", "Hand, foot and mouth disease") in rows
    assert ("R50.9", "index", "Fever") in rows
    assert not any(c == "R56.00" for c, _, _ in rows)  # code not in the kept list
    assert [r for r in rows if r[0] == "R50.9" and r[1] == "title"] == [("R50.9", "title", "Fever, unspecified")]


def test_shipped_code_file_is_well_formed():
    path = max((ROOT / "app" / "data").glob("icd10cm_*.tsv"))
    loaded = codes._load(path, path.stat().st_mtime)
    assert len(loaded.titles) > 30_000
    assert loaded.titles["A09"] == "Infectious gastroenteritis and colitis, unspecified"
    assert "Fever, enteric" in [loaded.phrase_texts[i] for i in np.flatnonzero(
        loaded.phrase_owner == loaded.position["A01.00"])]


# ---------- The code list ----------

def test_normalize_title_and_resolve():
    assert codes.normalize(" j189 ") == "J18.9" and codes.normalize("a09") == "A09"
    assert codes.title("j18.9") == "Pneumonia, unspecified organism"
    assert codes.title("Z99.99") is None
    resolved = codes.resolve(["a09", "E86.0", "A09"], limit=10)
    assert resolved == [
        {"code": "A09", "title": "Infectious gastroenteritis and colitis, unspecified"},
        {"code": "E86.0", "title": "Dehydration"},
    ]
    with pytest.raises(ValueError, match="Not ICD-10-CM codes: ZZZ.9"):
        codes.resolve(["A09", "ZZZ.9"], limit=10)
    with pytest.raises(ValueError, match="At most 1"):
        codes.resolve(["A09", "E86.0"], limit=1)


# ---------- Suggestions ----------

def test_typed_code_comes_first(client, ready_index):
    body = client.get("/api/codes/suggest", params={"q": "j18.9"}).json()
    assert body["items"][0] == {
        "code": "J18.9", "title": "Pneumonia, unspecified organism", "matched": None,
        "score": 1.0, "exact": True,
    }
    prefix = client.get("/api/codes/suggest", params={"q": "J18"}).json()["items"]
    assert {i["code"] for i in prefix if i["exact"]} >= {"J18.0", "J18.1", "J18.9"}


def test_clinical_wording_reaches_the_code_through_index_phrases(client, ready_index):
    enteric = client.get("/api/codes/suggest", params={"q": "enteric fever"}).json()["items"]
    assert enteric[0]["code"] == "A01.00"
    assert enteric[0]["matched"] == "Fever, enteric"
    hfmd = client.get("/api/codes/suggest", params={"q": "hand foot and mouth disease"}).json()["items"]
    assert "B08.4" in [i["code"] for i in hfmd[:3]]


def test_codes_the_clinic_uses_are_boosted(client, patient, ready_index):
    def score(code):
        items = client.get("/api/codes/suggest",
                           params={"q": "right lower lobe pneumonia", "limit": 20}).json()["items"]
        return next(i["score"] for i in items if i["code"] == code)

    before = score("J18.1")
    for _ in range(3):
        client.post("/api/records", json=make_record_payload(
            patient["id"], diagnosis="Lobar pneumonia", diagnosis_codes=[{"code": "J18.1"}]))
    db = SessionLocal()
    try:
        uses = codes.usage_counts(db)["J18.1"]
    finally:
        db.close()
    assert score("J18.1") == pytest.approx(before + codes.USAGE_BOOST * np.log1p(uses), abs=1e-4)


def test_status_reports_the_code_set(staff_client, ready_index):
    status = staff_client.get("/api/codes/status").json()
    assert status["state"] == "ready" and status["codes"] == 40
    assert status["code_set"] == "ICD-10-CM FY2027"
    assert status["done"] == status["total"] > 40


def test_vectors_are_cached_and_reloaded(ready_index, monkeypatch):
    path = codes.cache_path(codes.load())
    assert path.exists()
    fresh = codes._PhraseIndex()
    monkeypatch.setattr(codes, "index", fresh)
    started = time.monotonic()
    codes.build_index()
    assert fresh.state == "ready" and time.monotonic() - started < 5
    np.testing.assert_array_equal(np.asarray(fresh.matrix), np.asarray(ready_index.matrix))


def test_suggest_before_vectors_are_ready_still_answers_typed_codes(client, monkeypatch):
    monkeypatch.setattr(codes, "index", codes._PhraseIndex())
    body = client.get("/api/codes/suggest", params={"q": "A09"}).json()
    assert body["status"]["state"] == "not_started"
    assert [i["code"] for i in body["items"]] == ["A09"]
    assert client.get("/api/codes/suggest", params={"q": "enteric fever"}).json()["items"] == []


# ---------- Codes on records ----------

def test_record_stores_resolved_codes_and_audits_the_change(client, patient):
    rec = client.post("/api/records", json=make_record_payload(
        patient["id"], diagnosis_codes=[{"code": "a09"}, {"code": "E86.0", "title": "ignored"}],
    )).json()
    assert rec["diagnosis_codes"] == [
        {"code": "A09", "title": "Infectious gastroenteritis and colitis, unspecified"},
        {"code": "E86.0", "title": "Dehydration"},
    ]
    client.put(f"/api/records/{rec['id']}", json=make_record_payload(
        patient["id"], diagnosis_codes=[{"code": "A09"}]))
    row = client.get("/api/audit", params={"action": "record.update"}).json()["items"][0]
    assert "diagnosis_codes" in row["detail"]["fields"]
    cleared = client.put(f"/api/records/{rec['id']}", json=make_record_payload(patient["id"])).json()
    assert cleared["diagnosis_codes"] == []


def test_unknown_or_too_many_codes_are_rejected(client, patient):
    bad = client.post("/api/records", json=make_record_payload(
        patient["id"], diagnosis_codes=[{"code": "ZZZ.9"}]))
    assert bad.status_code == 422 and "ZZZ.9" in bad.json()["detail"]
    many = [{"code": c} for c in ("A09", "E86.0", "J18.9", "J18.1", "N10", "N39.0",
                                  "R56.00", "D50.9", "J21.9", "K52.9", "R50.9")]
    too_many = client.post("/api/records", json=make_record_payload(patient["id"], diagnosis_codes=many))
    assert too_many.status_code == 422
    assert config.MAX_DIAGNOSIS_CODES == 10


def test_records_are_searchable_by_code(client):
    p = client.post("/api/patients", json={"name": "Code Search Probe"}).json()
    rec = client.post("/api/records", json=make_record_payload(
        p["id"], diagnosis="Hand, foot and mouth disease", diagnosis_codes=[{"code": "B08.4"}])).json()
    hits = client.get("/api/search", params={"q": "B08.4"}).json()["hits"]
    hit = next(h for h in hits if h["record"]["id"] == rec["id"])
    assert hit["section"] == "diagnosis"
