"""AI drafting plumbing: de-identification, prompt building, retrieval of
style examples, response interpretation and the endpoint's guards.

No test here calls or imitates the model. Every request either stops before
the API call by design (switched off, no key, nothing to draft, too long) or
exercises code that runs on the API's response fields directly. The real
model is exercised in test_drafting_live.py.
"""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app import auth, config, schemas
from app.database import SessionLocal
from app.services import drafting
from tests.conftest import make_record_payload


@pytest.fixture()
def drafting_off(monkeypatch):
    monkeypatch.setattr(config, "LLM_ENABLED", False)


@pytest.fixture()
def drafting_on_without_key(monkeypatch):
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(config, "ANTHROPIC_KEY_FILE", config.DATA_DIR / "no-such-key-file.txt")


@pytest.fixture()
def drafting_on_with_unusable_key(monkeypatch):
    """Enabled with a key that would fail at the API. Only used by tests whose
    request must be rejected before any API call; if a guard regressed, the
    API would answer 401 and the test would fail rather than pass."""
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-invalid-test-key")
    monkeypatch.setattr(drafting, "_client", None)
    yield
    monkeypatch.setattr(drafting, "_client", None)


def _draft_audit_count(client) -> int:
    return client.get("/api/audit", params={"action": "record.draft"}).json()["total"]


# ---------- De-identification ----------

def test_deidentify_removes_names_ipd_phones_and_dates():
    text = (
        "Aarav Mehta, IPD-2026-114, was admitted on 12/07/2026 (2026-07-12T10:00). "
        "AARAV's mother (98250 12345, +91-9825012345) said aarav vomited. "
        "Seen by Dr. Mehta and Dr Mehta."
    )
    out = drafting.deidentify(text, names=["Aarav Mehta"], ipd_numbers=["IPD-2026-114"])
    for leaked in ("Aarav", "AARAV", "aarav", "IPD-2026-114", "12/07/2026",
                   "2026-07-12", "98250", "9825012345"):
        assert leaked not in out, leaked
    assert "the child, [IPD], was admitted on [date]" in out
    assert "the child's mother ([phone], [phone])" in out
    # The doctor's surname, often shared with patients, is left alone.
    assert "Dr. Mehta and Dr Mehta" in out


def test_deidentify_keeps_clinical_notation():
    text = "PCM 1-0-1, BP 104/70, SpO2 96%, platelets 1,20,000, 10-15 mg/kg"
    assert drafting.deidentify(text, names=["Riya Patel"]) == text


def test_deidentify_collapses_repeated_replacements_and_handles_empty():
    assert drafting.deidentify("Riya Patel Riya improved", names=["Riya Patel"]) == "the child improved"
    assert drafting.deidentify(None, names=["X"]) == ""
    assert drafting.deidentify("", names=[]) == ""


# ---------- Prompt construction ----------

def _fields(**overrides) -> schemas.DraftRequest:
    payload = make_record_payload(1, **overrides)
    payload.pop("patient_id")
    return schemas.DraftRequest(**payload)


def test_record_text_contains_clinical_facts_only():
    fields = _fields(
        history="Kabir Joshi had loose stools for 2 days; call 9876543210",
        ipd_number="IPD-77",
        course_in_hospital="IV fluids, improved",
        admission_date="2026-07-01T10:00:00", discharge_date="2026-07-04T09:00:00",
    )
    text = drafting.record_text(fields, sex="M", names=["Kabir Joshi"])
    assert "Kabir" not in text and "Joshi" not in text
    for absent in ("IPD-77", "9876543210", "Dr. Test", "T/1", "2026-07"):
        assert absent not in text, absent
    assert "Sex: M" in text
    assert "Length of stay: 3 days" in text
    assert "Diagnosis: Acute gastroenteritis with dehydration" in text
    assert "Signs present: dehydration" in text
    assert "Signs absent: pallor, icterus, rash, cyanosis, meningeal signs" in text
    assert "Treatment given in hospital:\n- IV RL 1 L IV 8 hourly 2 days" in text
    assert "Medicines on discharge:\n- ORS sachet 1 in 1 L PO After loose stool 3 days" in text
    assert "Doctor's notes for this section so far: IV fluids, improved" in text


def test_length_of_stay_edge_cases():
    day = datetime(2026, 7, 1, 10)
    assert drafting._length_of_stay(day, datetime(2026, 7, 1, 20)) == "less than a day"
    assert drafting._length_of_stay(day, datetime(2026, 7, 2, 9)) == "1 day"
    assert drafting._length_of_stay(day, datetime(2026, 6, 30)) is None
    assert drafting._length_of_stay(None, day) is None


def test_user_message_separates_current_record_from_examples():
    context = drafting.DraftContext(
        record_text="Diagnosis: Bronchiolitis",
        exemplars=[(7, "Diagnosis: Pneumonia\nCourse in hospital: Improved on IV antibiotics.")],
    )
    message = drafting.build_user_message(context)
    current = message.split("</current_record>")[0]
    assert "Bronchiolitis" in current and "Pneumonia" not in current
    assert '<case n="1">' in message and "Improved on IV antibiotics." in message
    empty = drafting.build_user_message(drafting.DraftContext(record_text="x", exemplars=[]))
    assert "<similar_cases>\n(none available)\n</similar_cases>" in empty


def test_has_clinical_content():
    assert drafting.has_clinical_content(_fields())
    blank = schemas.DraftRequest()
    assert not drafting.has_clinical_content(blank)
    assert drafting.has_clinical_content(schemas.DraftRequest(course_in_hospital="IV fluids"))


# ---------- Retrieval of style examples (real embedding model) ----------

DX = "Kawasaki disease with coronary artery ectasia"


def _record(client, name, **overrides):
    patient = client.post("/api/patients", json={"name": name}).json()
    record = client.post("/api/records", json=make_record_payload(
        patient["id"], diagnosis=DX, history="Fever for six days, red eyes, cracked lips",
        **overrides,
    )).json()
    return patient, record


def test_select_exemplars_uses_only_finalised_live_records_with_course(client):
    _, good = _record(client, "Zara Exemplar",
                      course_in_hospital="Zara Exemplar received IVIG on day 2 and defervesced.")
    _, draft = _record(client, "Draft Status", status="draft",
                       course_in_hospital="Draft record course")
    _, empty = _record(client, "Empty Course", course_in_hospital="   ")
    _, deleted = _record(client, "Deleted Case", course_in_hospital="Deleted record course")
    assert client.delete(f"/api/records/{deleted['id']}").status_code == 204
    current_patient, current = _record(client, "Current Child",
                                       course_in_hospital="Current record course")

    fields = _fields(diagnosis=DX, history="Fever for six days, red eyes, cracked lips")
    db = SessionLocal()
    try:
        exemplars, note = drafting.select_exemplars(
            db, fields, exclude_record_id=current["id"], limit=10,
        )
    finally:
        db.close()

    ids = [record_id for record_id, _ in exemplars]
    assert note is None
    assert good["id"] in ids
    for excluded in (draft, empty, deleted, current):
        assert excluded["id"] not in ids
    text = dict(exemplars)[good["id"]]
    assert "Zara" not in text and "Exemplar" not in text
    assert "the child received IVIG on day 2" in text
    assert text.startswith(f"Diagnosis: {DX}")


def test_select_exemplars_with_nothing_to_search():
    db = SessionLocal()
    try:
        assert drafting.select_exemplars(
            db, schemas.DraftRequest(), exclude_record_id=None, limit=3,
        ) == ([], None)
    finally:
        db.close()


# ---------- Response interpretation ----------

def test_interpret_refusal_names_category():
    with pytest.raises(drafting.DraftDeclined, match="category: general_harms"):
        drafting.interpret("refusal", None, SimpleNamespace(category="general_harms"))
    with pytest.raises(drafting.DraftDeclined):
        drafting.interpret("refusal", None, None)


def test_interpret_truncated_or_missing_output():
    with pytest.raises(drafting.DraftingFailed, match="cut off"):
        drafting.interpret("max_tokens", None)
    with pytest.raises(drafting.DraftingFailed, match="no usable draft"):
        drafting.interpret("end_turn", None)


def test_interpret_returns_parsed_draft():
    parsed = drafting.CourseDraft(course_in_hospital="Improved.", missing_information=[])
    assert drafting.interpret("end_turn", parsed) is parsed


def test_fallback_only_for_models_that_support_it():
    assert drafting._fallback_kwargs("claude-haiku-5-5") == {}
    assert drafting._fallback_kwargs("claude-sonnet-5-5") == {
        "betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default",
    }


def test_structured_output_schema_is_what_the_prompt_describes():
    schema = drafting.CourseDraft.model_json_schema()
    assert set(schema["required"]) == {"course_in_hospital", "missing_information"}
    assert "missing_information" in drafting.SYSTEM_PROMPT
    assert "course_in_hospital" in drafting.SYSTEM_PROMPT


# ---------- Limiter ----------

def test_sliding_window_limiter_is_per_key():
    limiter = auth.SlidingWindowLimiter(2, 60)
    assert limiter.check("1") and limiter.check("1")
    assert not limiter.check("1")
    assert limiter.check("2")


# ---------- Endpoint guards (nothing reaches the model) ----------

def test_status_and_draft_refused_when_switched_off(client, drafting_off):
    assert client.get("/api/draft/status").json() == {
        "enabled": False, "model": None,
        "reason": "AI drafting is switched off (DISCHARGE_LLM_ENABLED).",
    }
    before = _draft_audit_count(client)
    resp = client.post("/api/draft/course-in-hospital", json=make_record_payload(1))
    assert resp.status_code == 503
    assert "switched off" in resp.json()["detail"]
    assert _draft_audit_count(client) == before


def test_enabled_without_key_fails_loudly(staff_client, drafting_on_without_key):
    status = staff_client.get("/api/draft/status").json()
    assert status["enabled"] is False
    assert "ANTHROPIC_API_KEY" in status["reason"]
    resp = staff_client.post("/api/draft/course-in-hospital", json=make_record_payload(1))
    assert resp.status_code == 503
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_nothing_to_draft_is_rejected_before_the_model(client, drafting_on_with_unusable_key):
    assert client.get("/api/draft/status").json()["enabled"] is True
    before = _draft_audit_count(client)
    resp = client.post("/api/draft/course-in-hospital", json={})
    assert resp.status_code == 422
    assert "nothing to draft" in resp.json()["detail"]
    assert _draft_audit_count(client) == before


def test_record_and_patient_must_agree(client, patient, drafting_on_with_unusable_key):
    other = client.post("/api/patients", json={"name": "Other Child"}).json()
    record = client.post("/api/records", json=make_record_payload(patient["id"])).json()
    resp = client.post("/api/draft/course-in-hospital", json={
        **make_record_payload(other["id"]), "record_id": record["id"],
    })
    assert resp.status_code == 422
    assert "different patient" in resp.json()["detail"]
    missing = client.post("/api/draft/course-in-hospital", json={
        **make_record_payload(patient["id"]), "record_id": 999_999,
    })
    assert missing.status_code == 404


def test_oversized_record_is_refused_before_sending(drafting_on_with_unusable_key):
    context = drafting.DraftContext(record_text="x" * (drafting.MAX_INPUT_CHARS + 1), exemplars=[])
    with pytest.raises(drafting.DraftInputTooLong):
        drafting.draft_course(context)


def test_per_user_hourly_limit(client, patient, monkeypatch, drafting_on_with_unusable_key):
    from app.routers import drafting as drafting_router

    monkeypatch.setattr(drafting_router, "draft_limiter", auth.SlidingWindowLimiter(0, 3600))
    resp = client.post("/api/draft/course-in-hospital", json=make_record_payload(patient["id"]))
    assert resp.status_code == 429
    assert resp.headers["retry-after"] == "600"


def test_key_file_is_used_when_the_environment_has_no_key(tmp_path, monkeypatch):
    key_file = tmp_path / "anthropic_api_key.txt"
    key_file.write_text("  sk-ant-from-file  \n", encoding="utf-8")
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    monkeypatch.setattr(config, "ANTHROPIC_KEY_FILE", key_file)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert drafting._api_key() == "sk-ant-from-file"
    assert drafting.status().enabled is True

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
    assert drafting._api_key() == "sk-ant-from-env"  # the environment wins

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    key_file.write_text("\n", encoding="utf-8")
    assert drafting._api_key() is None
    assert drafting.status().enabled is False
