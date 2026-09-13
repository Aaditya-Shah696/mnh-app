"""Test setup: every test session runs against a throwaway data dir.

The embedding model is the REAL local fastembed model (cached on disk
after first download). Per project policy there is no mock fallback:
if the model cannot load, embedding-dependent tests fail loudly.
"""
import os
import sys
import tempfile
from pathlib import Path

# Must be set before the app modules are imported.
_tmp = tempfile.mkdtemp(prefix="discharge_test_")
os.environ["DISCHARGE_DATA_DIR"] = _tmp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    config.ensure_dirs()
    Base.metadata.create_all(engine)
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def patient(client):
    resp = client.post("/api/patients", json={
        "name": "Test Patient", "sex": "F", "dob": "1990-05-01",
        "chronic_conditions": "Hypothyroidism",
        "past_history": "LSCS 2018",
    })
    assert resp.status_code == 201
    return resp.json()


def make_record_payload(patient_id: int, **overrides) -> dict:
    payload = {
        "patient_id": patient_id,
        "ipd_number": "IPD-T-1",
        "ward": "T/1",
        "admission_date": "2026-07-01T10:00:00",
        "discharge_date": "2026-07-03T11:00:00",
        "age_at_admission": "36 y",
        "weight": "60 kg",
        "height": "160 cm",
        "diagnosis": "Acute gastroenteritis with dehydration",
        "history": "Loose stools and vomiting\n\nNo comorbidities",
        "examination_findings": "Conscious, oriented, mild dehydration",
        "temperature": "100.4 F",
        "pulse": "100/min",
        "bp": "104/70",
        "resp_rate": "18/min",
        "spo2": "98%",
        "pallor": "no",
        "icterus": "no",
        "rash": "no",
        "cyanosis": "no",
        "meningeal_signs": "no",
        "dehydration_signs": "yes",
        "throat_findings": "Normal",
        "respiratory_system": "Clear, equal air entry",
        "cvs_system": "S1 S2 normal",
        "abdominal_exam": "Soft, mild diffuse tenderness",
        "cns_system": "No deficit",
        "investigations": "CBC normal",
        "course_in_hospital": "IV fluids, improved",
        "advice": "ORS liberally",
        "follow_up_date": "2026-07-10",
        "follow_up_notes": "Review",
        "doctor_name": "Dr. Test",
        "status": "final",
        "treatment_items": [
            {"category": "hospital", "drug": "IV RL", "dose": "1 L",
             "route": "IV", "frequency": "8 hourly", "duration": "2 days"},
            {"category": "discharge", "drug": "ORS sachet", "dose": "1 in 1 L",
             "route": "PO", "frequency": "After loose stool", "duration": "3 days"},
        ],
    }
    payload.update(overrides)
    return payload
