"""Test setup: every test session runs against a throwaway data dir.

The embedding model is the REAL local fastembed model (cached on disk
after first download). Per project policy there is no mock fallback:
if the model cannot load, embedding-dependent tests fail loudly.

Authentication is real too: fixtures log in through POST /api/auth/login
and carry the session cookie. The TestClient base URL is https so the
Secure cookie is sent back, exactly as a browser would.
"""
import os
import sys
import tempfile
from pathlib import Path

# Must be set before the app modules are imported.
_tmp = tempfile.mkdtemp(prefix="discharge_test_")
os.environ["DISCHARGE_DATA_DIR"] = _tmp
os.environ.setdefault("DISCHARGE_PUBLIC_ORIGIN", "https://testserver")
# A small ICD-10-CM subset in the real file format, so building the code
# vectors takes seconds rather than minutes; no pauses between batches.
os.environ["DISCHARGE_ICD10_FILE"] = str(Path(__file__).resolve().parent / "fixtures" / "icd10cm_2027_sample.tsv")
os.environ["DISCHARGE_CODE_BUILD_PAUSE"] = "0"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import auth, config, models  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

ADMIN = {"username": "admin", "password": "admin-password-123", "display_name": "Dr. Test Admin"}
STAFF = {"username": "staff", "password": "staff-password-123", "display_name": "Reception"}


def _ensure_user(db, spec, role):
    user = db.query(models.User).filter_by(username=spec["username"]).first()
    if user is None:
        user = models.User(
            username=spec["username"], display_name=spec["display_name"], role=role,
            password_hash=auth.hash_password(spec["password"]), is_active=True,
        )
        db.add(user)
    else:
        user.password_hash = auth.hash_password(spec["password"])
        user.role, user.is_active = role, True
        auth.unlock_user(user)
    db.commit()
    return user.id


@pytest.fixture(scope="session", autouse=True)
def _database():
    config.ensure_dirs()
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        _ensure_user(db, ADMIN, "admin")
        _ensure_user(db, STAFF, "staff")
    finally:
        db.close()
    yield


def login(client: TestClient, spec) -> dict:
    resp = client.post("/api/auth/login", json={
        "username": spec["username"], "password": spec["password"],
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture()
def anon_client():
    with TestClient(app, base_url="https://testserver") as c:
        yield c


@pytest.fixture()
def client():
    """Logged in as admin (the role that can do everything)."""
    with TestClient(app, base_url="https://testserver") as c:
        login(c, ADMIN)
        yield c


@pytest.fixture()
def staff_client():
    with TestClient(app, base_url="https://testserver") as c:
        login(c, STAFF)
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


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    auth.login_ip_throttle.reset()
    yield
    auth.login_ip_throttle.reset()


def clear_login_failures():
    db = SessionLocal()
    try:
        db.query(models.LoginFailure).delete()
        db.query(models.User).update({"failed_logins": 0, "locked_until": None})
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _reset_login_failures():
    clear_login_failures()
    yield
    clear_login_failures()


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
