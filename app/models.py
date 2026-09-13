"""SQLAlchemy models mirroring the paper discharge card.

Vitals and dosing fields are short free-text strings on purpose: the
paper form takes values like "99.2 F", "84/min", "1-0-1", and forcing
numeric types would fight how the form is actually filled in.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    # Naive UTC: SQLite round-trips naive datetimes cleanly; aware ones do not.
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    records: Mapped[list["DischargeRecord"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan", order_by="DischargeRecord.id.desc()"
    )


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
