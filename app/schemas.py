"""Pydantic request/response schemas for the API."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

SEXES = {"M", "F", "Other"}
ROLES = {"admin", "staff"}
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,49}$")


# ---------- Auth / users ----------

class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def _norm_username(cls, v: str) -> str:
        return v.strip().lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    failed_logins: int = 0
    locked_until: datetime | None = None
    last_login_at: datetime | None = None
    password_changed_at: datetime | None = None
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    display_name: str = Field(min_length=1, max_length=120)
    role: str = "staff"
    password: str = Field(min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def _check_username(cls, v: str) -> str:
        v = v.strip().lower()
        if not USERNAME_RE.match(v):
            raise ValueError(
                "username must be 2-50 characters: lowercase letters, digits, . _ -"
            )
        return v

    @field_validator("display_name")
    @classmethod
    def _strip_display(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("display_name cannot be blank")
        return v

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str) -> str:
        if v not in ROLES:
            raise ValueError(f"role must be one of {sorted(ROLES)}")
        return v


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = None
    is_active: bool | None = None
    unlock: bool | None = None

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if v not in ROLES:
            raise ValueError(f"role must be one of {sorted(ROLES)}")
        return v

    @field_validator("display_name")
    @classmethod
    def _strip_display(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("display_name cannot be blank")
        return v


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=1, max_length=256)


# ---------- Audit ----------

class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ts: datetime
    user_id: int | None
    username: str | None
    action: str
    entity_type: str | None
    entity_id: int | None
    ip: str | None
    detail: dict[str, Any] | None = None

    @field_validator("detail", mode="before")
    @classmethod
    def _parse_detail(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {"raw": v}
        return v


class AuditPage(BaseModel):
    items: list[AuditOut]
    total: int
    limit: int
    offset: int
RECORD_STATUSES = {"draft", "final"}
TREATMENT_CATEGORIES = {"hospital", "discharge"}
SIGN_VALUES = {"yes", "no"}
SIGN_FIELDS = ("pallor", "icterus", "rash", "cyanosis", "meningeal_signs", "dehydration_signs")


# ---------- Patients ----------

class PatientBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sex: str | None = None
    dob: date | None = None
    chronic_conditions: str | None = None
    past_history: str | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be blank")
        return v

    @field_validator("sex")
    @classmethod
    def _check_sex(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if v not in SEXES:
            raise ValueError(f"sex must be one of {sorted(SEXES)}")
        return v


class PatientCreate(PatientBase):
    pass


class PatientUpdate(PatientBase):
    pass


class PatientOut(PatientBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ---------- Treatment items ----------

class TreatmentItemIn(BaseModel):
    category: str = "discharge"
    drug: str = Field(min_length=1, max_length=200)
    dose: str | None = Field(default=None, max_length=60)
    route: str | None = Field(default=None, max_length=30)
    frequency: str | None = Field(default=None, max_length=60)
    duration: str | None = Field(default=None, max_length=60)
    instructions: str | None = Field(default=None, max_length=300)
    position: int = 0

    @field_validator("category")
    @classmethod
    def _check_category(cls, v: str) -> str:
        if v not in TREATMENT_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(TREATMENT_CATEGORIES)}")
        return v

    @field_validator("drug")
    @classmethod
    def _strip_drug(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("drug cannot be blank")
        return v


class TreatmentItemOut(TreatmentItemIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


# ---------- Discharge records ----------

class RecordFields(BaseModel):
    ipd_number: str | None = Field(default=None, max_length=50)
    ward: str | None = Field(default=None, max_length=50)
    admission_date: datetime | None = None
    discharge_date: datetime | None = None
    age_at_admission: str | None = Field(default=None, max_length=20)
    weight: str | None = Field(default=None, max_length=20)
    height: str | None = Field(default=None, max_length=20)

    diagnosis: str | None = None
    history: str | None = None
    examination_findings: str | None = None

    temperature: str | None = Field(default=None, max_length=20)
    pulse: str | None = Field(default=None, max_length=20)
    bp: str | None = Field(default=None, max_length=20)
    resp_rate: str | None = Field(default=None, max_length=20)
    spo2: str | None = Field(default=None, max_length=20)

    pallor: str | None = None
    icterus: str | None = None
    rash: str | None = None
    cyanosis: str | None = None
    meningeal_signs: str | None = None
    dehydration_signs: str | None = None

    throat_findings: str | None = None
    respiratory_system: str | None = None
    cvs_system: str | None = None
    abdominal_exam: str | None = None
    cns_system: str | None = None

    investigations: str | None = None
    course_in_hospital: str | None = None

    advice: str | None = None
    follow_up_date: date | None = None
    follow_up_notes: str | None = Field(default=None, max_length=300)
    doctor_name: str | None = Field(default=None, max_length=120)

    status: str = "draft"

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in RECORD_STATUSES:
            raise ValueError(f"status must be one of {sorted(RECORD_STATUSES)}")
        return v

    @field_validator(*SIGN_FIELDS)
    @classmethod
    def _check_sign(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if v not in SIGN_VALUES:
            raise ValueError(f"sign must be one of {sorted(SIGN_VALUES)} or null")
        return v


class RecordCreate(RecordFields):
    patient_id: int
    treatment_items: list[TreatmentItemIn] = []


class RecordUpdate(RecordFields):
    treatment_items: list[TreatmentItemIn] = []


class RecordSummary(BaseModel):
    """Lightweight record for lists and match results."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    patient_name: str = ""
    diagnosis: str | None
    admission_date: datetime | None
    discharge_date: datetime | None
    status: str
    deleted_at: datetime | None = None
    updated_at: datetime


class RecordOut(RecordFields):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    treatment_items: list[TreatmentItemOut] = []
    patient: PatientOut
    deleted_at: datetime | None = None
    created_by: int | None = None
    updated_by: int | None = None
    created_at: datetime
    updated_at: datetime


# ---------- Matching (Step 4) ----------

class MatchQuery(BaseModel):
    text: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)
    exclude_record_id: int | None = None


class MatchResult(BaseModel):
    score: float
    record: RecordOut
