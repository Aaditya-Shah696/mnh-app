"""Application configuration.

All persistent data lives under DATA_DIR so a single folder holds the
database, attachments, and backups. Clinic letterhead details are read
from data/clinic.json so they can be edited without touching code.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("DISCHARGE_DATA_DIR", PROJECT_ROOT / "data"))
# The attachments feature was removed, but files uploaded before removal
# still live here and are still swept into every encrypted backup.
ATTACHMENTS_DIR = DATA_DIR / "attachments"
BACKUPS_DIR = Path(os.environ.get("DISCHARGE_BACKUP_DIR", DATA_DIR / "backups"))
DB_PATH = DATA_DIR / "discharge.db"
DATABASE_URL = os.environ.get("DISCHARGE_DATABASE_URL", f"sqlite:///{DB_PATH}")

# Embedding model used for the similar-record recommender. Small, local,
# downloaded once by fastembed and cached under ~/.cache.
EMBEDDING_MODEL = os.environ.get("DISCHARGE_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

# Hours between automatic backups while the app is running.
BACKUP_INTERVAL_HOURS = float(os.environ.get("DISCHARGE_BACKUP_INTERVAL_HOURS", "24"))

# "production" disables the interactive API docs and refuses demo seeding.
ENV = os.environ.get("DISCHARGE_ENV", "development").strip().lower()
IS_PRODUCTION = ENV == "production"

# The origin the app is served from in production (e.g. https://mnh.example.com).
# Used by the CSRF Origin check in addition to the request's own Host header.
PUBLIC_ORIGIN = os.environ.get("DISCHARGE_PUBLIC_ORIGIN", "").strip().rstrip("/").lower()

# ---- Authentication -------------------------------------------------------
SESSION_COOKIE_NAME = "mnh_session"
# A session dies after this many hours without a request...
SESSION_IDLE_HOURS = float(os.environ.get("DISCHARGE_SESSION_IDLE_HOURS", "12"))
# ...and unconditionally after this many days since login.
SESSION_MAX_DAYS = float(os.environ.get("DISCHARGE_SESSION_MAX_DAYS", "14"))
# last_seen_at is written at most this often so a busy user does not cost a
# write per request.
SESSION_TOUCH_SECONDS = 300
# Chrome/Edge/Firefox accept Secure cookies on http://localhost, so this stays
# on for local development too. Set DISCHARGE_COOKIE_SECURE=0 only for an odd
# browser; the app logs a warning at startup when it is off.
COOKIE_SECURE = os.environ.get("DISCHARGE_COOKIE_SECURE", "1").strip() != "0"

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 256

# Account lockout: after LOGIN_LOCK_THRESHOLD consecutive failures the account
# locks for LOGIN_LOCK_BASE_MINUTES, doubling per further failure up to
# LOGIN_LOCK_MAX_HOURS. Stored on the user row so it survives restarts.
LOGIN_LOCK_THRESHOLD = 5
LOGIN_LOCK_BASE_MINUTES = 15
LOGIN_LOCK_MAX_HOURS = 24
# Per-IP throttle on /api/auth/login (in-process; the app runs one worker).
LOGIN_IP_LIMIT = 30
LOGIN_IP_WINDOW_SECONDS = 600

# Printed on every discharge card, before the signature. Editable in
# data/clinic.json; sourced from WHO/IMCI general danger signs and
# standard safety-netting advice.
DEFAULT_WARNING_SIGNS = (
    "Warning signs — seek medical care immediately if you notice any of these: "
    "high fever not controlled by medicine or lasting more than three days, "
    "difficulty or fast breathing, chest indrawing or bluish lips, persistent "
    "vomiting or inability to keep fluids or food down, signs of dehydration "
    "such as little or no urine, dry mouth, sunken eyes or no tears, excessive "
    "drowsiness, confusion or difficulty waking, fits or convulsions, severe or "
    "worsening chest, abdominal or head pain, any bleeding, black stools or "
    "blood in vomit or urine, neck stiffness or a rash with high fever, or "
    "being unable to eat or drink (in young children, unable to feed). "
    "Return on your follow-up date, or sooner if any of these appear."
)

_DEFAULT_CLINIC = {
    "clinic_name": "Mahavir Nursing Home",
    "clinic_subtitle": "",
    "address_line1": "",
    "address_line2": "",
    "phone": "",
    "doctor_name": "",
    "doctor_qualifications": "",
    "registration_number": "",
    "warning_signs": DEFAULT_WARNING_SIGNS,
}


def clinic_info() -> dict:
    """Letterhead details for the UI header and PDF export."""
    path = DATA_DIR / "clinic.json"
    info = dict(_DEFAULT_CLINIC)
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                info.update({k: str(v) for k, v in loaded.items() if k in info})
        except (json.JSONDecodeError, OSError):
            pass
    return info


def ensure_dirs() -> None:
    for d in (DATA_DIR, ATTACHMENTS_DIR, BACKUPS_DIR):
        d.mkdir(parents=True, exist_ok=True)
