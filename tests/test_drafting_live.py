"""Live test of AI drafting against the REAL Anthropic API.

There is deliberately no mocked model: without ANTHROPIC_API_KEY this test
skips and says so. With a key it costs a few US cents per run and sends only
the synthetic records created below.
"""
import os
from pathlib import Path

import pytest

from app import config
from app.services import drafting
from tests.conftest import make_record_payload

# The suite runs on a throwaway data dir, so look for the developer's key
# file in the real one (data/anthropic_api_key.txt) as well as the env.
_REAL_KEY_FILE = Path(__file__).resolve().parent.parent / "data" / "anthropic_api_key.txt"
_KEY_FILE_HAS_KEY = _REAL_KEY_FILE.is_file() and bool(_REAL_KEY_FILE.read_text(encoding="utf-8").strip())

pytestmark = pytest.mark.skipif(
    not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or _KEY_FILE_HAS_KEY),
    reason="no Anthropic API key (env or data/anthropic_api_key.txt): "
           "the live drafting test needs the real API (no mock by design)",
)

EXEMPLAR_ONLY_DRUG = "ondansetron"


@pytest.fixture()
def drafting_live(monkeypatch):
    monkeypatch.setattr(config, "LLM_ENABLED", True)
    if _KEY_FILE_HAS_KEY:
        monkeypatch.setattr(config, "ANTHROPIC_KEY_FILE", _REAL_KEY_FILE)
    monkeypatch.setattr(drafting, "_client", None)
    yield
    monkeypatch.setattr(drafting, "_client", None)


def test_live_draft_is_grounded_and_deidentified(client, drafting_live):
    # A finalised past case that will be retrieved as a style example. Its
    # distinctive drug and its patient's name must not leak into the draft.
    past = client.post("/api/patients", json={"name": "Ishaan Exemplarson", "sex": "M"}).json()
    client.post("/api/records", json=make_record_payload(
        past["id"],
        age_at_admission="9 months", weight="8 kg",
        diagnosis="Acute bronchiolitis",
        history="Cough and fast breathing for 2 days",
        course_in_hospital=(
            "Ishaan Exemplarson was admitted with acute bronchiolitis and needed oxygen "
            f"for one day. He vomited twice and was given {EXEMPLAR_ONLY_DRUG}. Feeds were "
            "established by day 2 and he was discharged in a stable condition."
        ),
        treatment_items=[{"category": "hospital", "drug": "Oxygen", "dose": "1 L/min",
                          "route": "nasal prongs", "frequency": "continuous",
                          "duration": "1 day"}],
    ))

    current = client.post("/api/patients", json={"name": "Vihaan Testcase", "sex": "M"}).json()
    payload = make_record_payload(
        current["id"],
        age_at_admission="7 months", weight="7.5 kg", height="66 cm",
        diagnosis="Acute bronchiolitis",
        history="Vihaan Testcase had cough, coryza and fast breathing for 3 days; feeding poorly.",
        examination_findings="Tachypnoeic, subcostal retractions",
        temperature="99.8 F", pulse="148/min", resp_rate="58/min", spo2="91% on room air",
        dehydration_signs="no",
        respiratory_system="Bilateral wheeze and fine crepitations",
        investigations="CBC: TLC 9800, CRP negative",
        course_in_hospital="O2 via nasal prongs, nebulised 3% saline. O2 weaned day 2. Feeding well at discharge.",
        advice="Continue breastfeeding, saline nasal drops",
        treatment_items=[
            {"category": "hospital", "drug": "Oxygen", "dose": "1 L/min",
             "route": "nasal prongs", "frequency": "continuous", "duration": "2 days"},
            {"category": "hospital", "drug": "Nebulised 3% saline", "dose": "3 ml",
             "route": "nebulisation", "frequency": "6 hourly", "duration": "3 days"},
            {"category": "discharge", "drug": "Saline nasal drops", "dose": "2 drops",
             "route": "nasal", "frequency": "TDS", "duration": "5 days"},
        ],
    )
    payload.pop("patient_id")
    resp = client.post("/api/draft/course-in-hospital", json={**payload, "patient_id": current["id"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    draft = body["course_in_hospital"]
    print("\nLIVE DRAFT:", draft, "\nMISSING:", body["missing_information"], "\nMODEL:", body["model"])

    assert draft.strip(), "model returned an empty draft for a complete record"
    lowered = draft.lower()
    for leaked in ("vihaan", "testcase", "ishaan", "exemplarson"):
        assert leaked not in lowered, f"identifier leaked into the draft: {leaked}"
    assert EXEMPLAR_ONLY_DRUG not in lowered, "a fact from a past case was copied into the draft"
    assert "saline" in lowered or "oxygen" in lowered or "o2" in lowered
    assert isinstance(body["missing_information"], list)
    assert body["model"].startswith("claude-")

    audit = client.get("/api/audit", params={"action": "record.draft"}).json()["items"][0]
    assert audit["action"] == "record.draft"
    assert audit["detail"]["outcome"] == "drafted"
    assert audit["detail"]["input_tokens"] > 0
    assert audit["detail"]["patient_id"] == current["id"]
