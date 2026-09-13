"""SQLAlchemy models mirroring the paper discharge card.

Vitals and dosing fields are short free-text strings on purpose: the
paper form takes values like "99.2 F", "84/min", "1-0-1", and forcing
numeric types would fight how the form is actually filled in.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, DDL, ForeignKey, Integer, LargeBinary, String, Text, event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    # Naive UTC: SQLite round-trips naive datetimes cleanly; aware ones do not.
    return datetime.now(timezone.utc).replace(tzinfo=None)


ROLES = ("admin", "staff")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # lowercased
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))  # argon2id PHC string
    role: Mapped[str] = mapped_column(String(10), default="staff")  # admin | staff
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class UserSession(Base):
    """Server-side session. The raw token lives only in the browser cookie;
    the table stores its SHA-256 so a leaked database cannot be replayed."""
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped[User] = relationship(back_populates="sessions")


class AuditLog(Base):
    """Append-only. Two SQLite triggers (AUDIT_LOG_TRIGGERS) refuse UPDATE and
    DELETE on this table even for someone with the database file open."""
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)  # no FK: rows outlive users
    username: Mapped[str | None] = mapped_column(String(50), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(20))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    ip: Mapped[str | None] = mapped_column(String(45))
    detail: Mapped[str | None] = mapped_column(Text)  # small JSON, never field values


AUDIT_LOG_TRIGGERS = (
    "CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log "
    "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log "
    "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END",
)

for _ddl in AUDIT_LOG_TRIGGERS:
    # Fires for Base.metadata.create_all (tests, fresh installs). The Alembic
    # migration executes the same statements explicitly.
    event.listen(AuditLog.__table__, "after_create", DDL(_ddl).execute_if(dialect="sqlite"))


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    sex: Mapped[str | None] = mapped_column(String(10))
    dob: Mapped[date | None] = mapped_column(Date)
    # Persistent across visits: prefilled into each new discharge and
    # written back when the discharge is saved (profile is source of truth).
    chronic_conditions: Mapped[str | None] = mapped_column(Text)
    past_history: Mapped[str | None] = mapped_column(Text)
    # Soft delete: set instead of removing the row; admin can restore.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    records: Mapped[list["DischargeRecord"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan", order_by="DischargeRecord.id.desc()"
    )

    @property
    def active_records(self) -> list["DischargeRecord"]:
        return [r for r in self.records if r.deleted_at is None]


class DischargeRecord(Base):
    __tablename__ = "discharge_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )

    # Admission block
    ipd_number: Mapped[str | None] = mapped_column(String(50), index=True)
    ward: Mapped[str | None] = mapped_column(String(50))
    admission_date: Mapped[datetime | None] = mapped_column(DateTime)
    discharge_date: Mapped[datetime | None] = mapped_column(DateTime)
    age_at_admission: Mapped[str | None] = mapped_column(String(20))
    weight: Mapped[str | None] = mapped_column(String(20))
    height: Mapped[str | None] = mapped_column(String(20))

    # Clinical block
    diagnosis: Mapped[str | None] = mapped_column(Text)
    history: Mapped[str | None] = mapped_column(Text)
    examination_findings: Mapped[str | None] = mapped_column(Text)  # "General examination"

    # Examination findings: vitals on admission
    temperature: Mapped[str | None] = mapped_column(String(20))
    pulse: Mapped[str | None] = mapped_column(String(20))
    bp: Mapped[str | None] = mapped_column(String(20))
    resp_rate: Mapped[str | None] = mapped_column(String(20))
    spo2: Mapped[str | None] = mapped_column(String(20))

    # Examination findings: signs, "yes"/"no" ("no" covers unticked; NULL
    # only on records saved before these fields existed)
    pallor: Mapped[str | None] = mapped_column(String(3))
    icterus: Mapped[str | None] = mapped_column(String(3))
    rash: Mapped[str | None] = mapped_column(String(3))
    cyanosis: Mapped[str | None] = mapped_column(String(3))
    meningeal_signs: Mapped[str | None] = mapped_column(String(3))
    dehydration_signs: Mapped[str | None] = mapped_column(String(3))

    # Examination findings: per-system free text
    throat_findings: Mapped[str | None] = mapped_column(Text)
    respiratory_system: Mapped[str | None] = mapped_column(Text)
    cvs_system: Mapped[str | None] = mapped_column(Text)
    abdominal_exam: Mapped[str | None] = mapped_column(Text)
    cns_system: Mapped[str | None] = mapped_column(Text)

    investigations: Mapped[str | None] = mapped_column(Text)
    course_in_hospital: Mapped[str | None] = mapped_column(Text)

    # Discharge block
    advice: Mapped[str | None] = mapped_column(Text)
    follow_up_date: Mapped[date | None] = mapped_column(Date)
    follow_up_notes: Mapped[str | None] = mapped_column(String(300))
    doctor_name: Mapped[str | None] = mapped_column(String(120))

    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft | final

    # Recommender: embedding of diagnosis + history + treatment text
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(100))

    # Soft delete (see Patient.deleted_at). Deleted records are hidden from
    # lists, profiles and the similar-case matcher.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    # NULL on the rows that predate authentication.
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    patient: Mapped[Patient] = relationship(back_populates="records")
    treatment_items: Mapped[list["TreatmentItem"]] = relationship(
        back_populates="record", cascade="all, delete-orphan", order_by="TreatmentItem.position"
    )


class TreatmentItem(Base):
    __tablename__ = "treatment_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("discharge_records.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(10), default="discharge")  # hospital | discharge
    drug: Mapped[str] = mapped_column(String(200))
    dose: Mapped[str | None] = mapped_column(String(60))
    route: Mapped[str | None] = mapped_column(String(30))
    frequency: Mapped[str | None] = mapped_column(String(60))
    duration: Mapped[str | None] = mapped_column(String(60))
    instructions: Mapped[str | None] = mapped_column(String(300))
    position: Mapped[int] = mapped_column(Integer, default=0)

    record: Mapped[DischargeRecord] = relationship(back_populates="treatment_items")
