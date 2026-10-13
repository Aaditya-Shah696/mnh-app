from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import auth, models, schemas
from ..audit import audit, changed_fields
from ..database import get_db
from ..querying import contains_pattern
from ..models import utcnow
from ..services import search

router = APIRouter(
    prefix="/api/patients", tags=["patients"], dependencies=[Depends(auth.current_user)]
)


def get_patient_or_404(
    patient_id: int, db: Session, *, include_deleted: bool = False
) -> models.Patient:
    patient = db.get(models.Patient, patient_id)
    if patient is None or (patient.deleted_at is not None and not include_deleted):
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


def _summary(patient: models.Patient, r: models.DischargeRecord) -> schemas.RecordSummary:
    return schemas.RecordSummary(
        id=r.id,
        patient_id=r.patient_id,
        patient_name=patient.name,
        diagnosis=r.diagnosis,
        admission_date=r.admission_date,
        discharge_date=r.discharge_date,
        status=r.status,
        deleted_at=r.deleted_at,
        updated_at=r.updated_at,
    )


@router.post("", response_model=schemas.PatientOut, status_code=201)
def create_patient(
    payload: schemas.PatientCreate, request: Request,
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    patient = models.Patient(**payload.model_dump())
    db.add(patient)
    db.flush()
    audit(db, "patient.create", request=request, user=user,
          entity_type="patient", entity_id=patient.id)
    db.commit()
    db.refresh(patient)
    return patient


@router.get("", response_model=list[schemas.PatientOut])
def list_patients(
    q: str | None = Query(default=None, description="Search by name"),
    limit: int = Query(default=50, ge=1, le=200),
    deleted: bool = Query(default=False, description="Admin only: list deleted patients"),
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    if deleted and not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    visibility = (
        models.Patient.deleted_at.is_not(None) if deleted else models.Patient.deleted_at.is_(None)
    )
    stmt = select(models.Patient).where(visibility)
    if q:
        like = contains_pattern(q.strip())
        stmt = stmt.where(
            models.Patient.name.ilike(like, escape="\\")
        ).order_by(models.Patient.name)
    else:
        stmt = stmt.order_by(models.Patient.updated_at.desc())
    return db.scalars(stmt.limit(limit)).all()


@router.get("/{patient_id}", response_model=schemas.PatientOut)
def get_patient(
    patient_id: int, request: Request,
    include_deleted: bool = Query(default=False),
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    if include_deleted and not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    patient = get_patient_or_404(patient_id, db, include_deleted=include_deleted)
    audit(db, "patient.view", request=request, user=user,
          entity_type="patient", entity_id=patient.id)
    db.commit()
    return patient


@router.get("/{patient_id}/records", response_model=list[schemas.RecordSummary])
def patient_records(
    patient_id: int,
    include_deleted: bool = Query(default=False),
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    if include_deleted and not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    patient = get_patient_or_404(patient_id, db, include_deleted=include_deleted)
    records = patient.records if include_deleted else patient.active_records
    return [_summary(patient, r) for r in records]


@router.put("/{patient_id}", response_model=schemas.PatientOut)
def update_patient(
    patient_id: int, payload: schemas.PatientUpdate, request: Request,
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    patient = get_patient_or_404(patient_id, db)
    after = payload.model_dump()
    before = {k: getattr(patient, k) for k in after}
    for key, value in after.items():
        setattr(patient, key, value)
    if before.get("name") != patient.name:
        db.flush()
        search.index_records(db, [r.id for r in patient.records])
    audit(db, "patient.update", request=request, user=user, entity_type="patient",
          entity_id=patient.id, detail={"fields": changed_fields(before, after)})
    db.commit()
    db.refresh(patient)
    return patient


@router.delete("/{patient_id}", status_code=204)
def delete_patient(
    patient_id: int, request: Request,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    """Soft-delete the patient and every active discharge record. Restorable."""
    patient = get_patient_or_404(patient_id, db)
    now = utcnow()
    patient.deleted_at = now
    record_ids = []
    for record in patient.active_records:
        record.deleted_at = now
        record_ids.append(record.id)
    audit(db, "patient.delete", request=request, user=admin, entity_type="patient",
          entity_id=patient.id, detail={"records": record_ids})
    db.commit()


@router.post("/{patient_id}/restore", response_model=schemas.PatientOut)
def restore_patient(
    patient_id: int, request: Request,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    """Restore a deleted patient plus the records deleted together with them."""
    patient = db.get(
        models.Patient, patient_id, options=[selectinload(models.Patient.records)]
    )
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient.deleted_at is None:
        raise HTTPException(status_code=409, detail="Patient is not deleted")
    stamp = patient.deleted_at
    restored = []
    for record in patient.records:
        if record.deleted_at == stamp:
            record.deleted_at = None
            restored.append(record.id)
    patient.deleted_at = None
    audit(db, "patient.restore", request=request, user=admin, entity_type="patient",
          entity_id=patient.id, detail={"records": restored})
    db.commit()
    db.refresh(patient)
    return patient
