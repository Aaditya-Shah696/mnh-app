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

_DEFAULT_CLINIC = {
    "clinic_name": "MNH Nursing Home",
    "clinic_subtitle": "",
    "address_line1": "",
    "address_line2": "",
    "phone": "",
    "doctor_name": "",
    "doctor_qualifications": "",
    "registration_number": "",
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
