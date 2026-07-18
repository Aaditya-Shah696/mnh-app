from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/patients", tags=["patients"])


def get_patient_or_404(patient_id: int, db: Session) -> models.Patient:
    patient = db.get(models.Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.post("", response_model=schemas.PatientOut, status_code=201)
def create_patient(payload: schemas.PatientCreate, db: Session = Depends(get_db)):
    patient = models.Patient(**payload.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@router.get("", response_model=list[schemas.PatientOut])
def list_patients(
    q: str | None = Query(default=None, description="Search by name or phone"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    stmt = select(models.Patient).order_by(models.Patient.updated_at.desc()).limit(limit)
    if q:
        like = f"%{q.strip()}%"
        stmt = (
            select(models.Patient)
            .where(or_(models.Patient.name.ilike(like), models.Patient.phone.ilike(like)))
            .order_by(models.Patient.name)
            .limit(limit)
        )
    return db.scalars(stmt).all()


@router.get("/{patient_id}", response_model=schemas.PatientOut)
def get_patient(patient_id: int, db: Session = Depends(get_db)):
    return get_patient_or_404(patient_id, db)


@router.get("/{patient_id}/records", response_model=list[schemas.RecordSummary])
def patient_records(patient_id: int, db: Session = Depends(get_db)):
    patient = get_patient_or_404(patient_id, db)
    return [
        schemas.RecordSummary(
            id=r.id,
            patient_id=r.patient_id,
            patient_name=patient.name,
            diagnosis=r.diagnosis,
            admission_date=r.admission_date,
            discharge_date=r.discharge_date,
            status=r.status,
            updated_at=r.updated_at,
        )
        for r in patient.records
    ]


@router.put("/{patient_id}", response_model=schemas.PatientOut)
def update_patient(patient_id: int, payload: schemas.PatientUpdate, db: Session = Depends(get_db)):
    patient = get_patient_or_404(patient_id, db)
    for key, value in payload.model_dump().items():
        setattr(patient, key, value)
    db.commit()
    db.refresh(patient)
    return patient


@router.delete("/{patient_id}", status_code=204)
def delete_patient(patient_id: int, db: Session = Depends(get_db)):
    patient = get_patient_or_404(patient_id, db)
    if patient.records:
        raise HTTPException(
            status_code=409,
            detail="Patient has discharge records; delete those first.",
        )
    db.delete(patient)
    db.commit()
