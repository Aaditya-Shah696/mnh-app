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
ATTACHMENTS_DIR = DATA_DIR / "attachments"
BACKUPS_DIR = Path(os.environ.get("DISCHARGE_BACKUP_DIR", DATA_DIR / "backups"))
DB_PATH = DATA_DIR / "discharge.db"
DATABASE_URL = os.environ.get("DISCHARGE_DATABASE_URL", f"sqlite:///{DB_PATH}")

# Embedding model used for the similar-record recommender. Small, local,
# downloaded once by fastembed and cached under ~/.cache.
EMBEDDING_MODEL = os.environ.get("DISCHARGE_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

MAX_ATTACHMENT_MB = int(os.environ.get("DISCHARGE_MAX_ATTACHMENT_MB", "25"))
ALLOWED_ATTACHMENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Hours between automatic backups while the app is running.
BACKUP_INTERVAL_HOURS = float(os.environ.get("DISCHARGE_BACKUP_INTERVAL_HOURS", "24"))

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
