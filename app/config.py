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

# Account lockout: after LOGIN_LOCK_THRESHOLD consecutive failures for a
# username from one address, that address is locked out of that username for
# LOGIN_LOCK_BASE_MINUTES, doubling per further failure up to
# LOGIN_LOCK_MAX_HOURS. Stored in login_failures so it survives restarts.
LOGIN_LOCK_THRESHOLD = 5
LOGIN_LOCK_BASE_MINUTES = 15
LOGIN_LOCK_MAX_HOURS = 24
LOGIN_FAILURE_RESET_HOURS = 24
# Per-IP throttle on /api/auth/login (in-process; the app runs one worker).
LOGIN_IP_LIMIT = 30
LOGIN_IP_WINDOW_SECONDS = 600

MATCH_VIEW_AUDIT_MINUTES = 60

# ---- Search ---------------------------------------------------------------
# Records containing the typed words always come first. Records related only
# by meaning follow, at most SEARCH_MAX_MEANING_HITS of them, and only if
# they stand out from the query's scores over every record (z-score at least
# SEARCH_MIN_ZSCORE) and reach SEARCH_MIN_SIMILARITY. bge-small similarities
# are compressed (noise ~0.5-0.6, real matches ~0.65-0.8), so a fixed cut-off
# alone gave ~0.4 precision on the 18-query check over the 19 demo records;
# this rule gave 0.78 precision at 0.61 recall. Re-tune on real records once
# the old cards are imported. Below SEARCH_MIN_CORPUS records a z-score means
# little, so meaning only re-orders word matches.
SEARCH_MIN_SIMILARITY = float(os.environ.get("DISCHARGE_SEARCH_MIN_SIMILARITY", "0.55"))
SEARCH_MIN_ZSCORE = float(os.environ.get("DISCHARGE_SEARCH_MIN_ZSCORE", "1.75"))
SEARCH_MIN_CORPUS = 10
SEARCH_MAX_MEANING_HITS = 5
# Shorter queries (initials, two-letter fragments) are keyword-only.
SEARCH_SEMANTIC_MIN_CHARS = 4

# ---- ICD-10-CM diagnosis codes -------------------------------------------
# The newest app/data/icd10cm_<year>.tsv unless DISCHARGE_ICD10_FILE names one.
ICD10_DATA_DIR = PROJECT_ROOT / "app" / "data"
ICD10_FILE = os.environ.get("DISCHARGE_ICD10_FILE", "").strip()
# Derived phrase vectors (~70 MB). Not in the database, not in backups.
CODE_CACHE_DIR = Path(os.environ.get("DISCHARGE_CODE_CACHE_DIR", DATA_DIR / "cache"))
# Seconds slept between embedding batches while building in the background,
# so the one-off build leaves CPU for requests on the 2-vCPU VPS.
CODE_BUILD_PAUSE = float(os.environ.get("DISCHARGE_CODE_BUILD_PAUSE", "0.05"))
MAX_DIAGNOSIS_CODES = 10

# ---- Duplicate-entry warning -----------------------------------------------
# A new record is flagged when the same patient already has a live record
# admitted the same day, or one this similar admitted within the window.
DUPLICATE_SIMILARITY = 0.97
DUPLICATE_WINDOW_DAYS = 7

# ---- AI drafting (optional, off by default) --------------------------------
# Drafts the "Course in hospital" text with Claude for the doctor to review.
# Needs DISCHARGE_LLM_ENABLED=1 and an API key: ANTHROPIC_API_KEY in the
# environment (on the VPS: /srv/mnh/mnh.env), or the key alone in
# ANTHROPIC_KEY_FILE (git-ignored, never in backups). Identifiers are
# stripped before anything is sent; see app/services/drafting.py.
ANTHROPIC_KEY_FILE = Path(os.environ.get("DISCHARGE_ANTHROPIC_KEY_FILE", DATA_DIR / "anthropic_api_key.txt"))
LLM_ENABLED = os.environ.get("DISCHARGE_LLM_ENABLED", "0").strip() == "1"
LLM_MODEL = os.environ.get("DISCHARGE_LLM_MODEL", "claude-sonnet-5-5").strip()
# The doctor waits on this button, so medium rather than the model's default
# high. Raise it only if the 60-card evaluation shows better drafts.
LLM_EFFORT = os.environ.get("DISCHARGE_LLM_EFFORT", "medium").strip()
LLM_MAX_TOKENS = 8000
LLM_TIMEOUT_SECONDS = 90.0
# Past cases sent as style examples (their "course in hospital" text only).
LLM_EXEMPLARS = 3
# Per-user cap on drafts, a cost and runaway-loop brake.
LLM_USER_HOURLY_LIMIT = int(os.environ.get("DISCHARGE_LLM_HOURLY_LIMIT", "30"))

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
