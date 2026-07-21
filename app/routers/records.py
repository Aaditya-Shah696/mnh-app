from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import config, models, schemas
from ..database import get_db
from ..services import embeddings, pdf_export
from .patients import get_patient_or_404

router = APIRouter(prefix="/api/records", tags=["records"])


def get_record_or_404(record_id: int, db: Session) -> models.DischargeRecord:
    record = db.get(
        models.DischargeRecord,
        record_id,
        options=[
            selectinload(models.DischargeRecord.treatment_items),
            selectinload(models.DischargeRecord.attachments),
            selectinload(models.DischargeRecord.patient),
        ],
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


def _apply_fields(record: models.DischargeRecord, fields: schemas.RecordFields) -> None:
    for key, value in fields.model_dump(exclude={"treatment_items", "patient_id"}).items():
        setattr(record, key, value)


def _replace_treatment_items(
    record: models.DischargeRecord, items: list[schemas.TreatmentItemIn]
) -> None:
    record.treatment_items.clear()
    for i, item in enumerate(items):
        data = item.model_dump()
        data["position"] = i
        record.treatment_items.append(models.TreatmentItem(**data))


@router.post("", response_model=schemas.RecordOut, status_code=201)
def create_record(payload: schemas.RecordCreate, db: Session = Depends(get_db)):
    get_patient_or_404(payload.patient_id, db)
    record = models.DischargeRecord(patient_id=payload.patient_id)
    _apply_fields(record, payload)
    _replace_treatment_items(record, payload.treatment_items)
    db.add(record)
    db.flush()
    embeddings.refresh_record_embedding(record)
    db.commit()
    return get_record_or_404(record.id, db)


@router.get("", response_model=list[schemas.RecordSummary])
def list_records(
    q: str | None = Query(default=None, description="Filter by patient name"),
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    stmt = (
        select(models.DischargeRecord)
        .options(selectinload(models.DischargeRecord.patient))
        .order_by(models.DischargeRecord.updated_at.desc())
        .limit(limit)
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.join(models.DischargeRecord.patient).where(
            models.Patient.name.ilike(like)
        )
    return [
        schemas.RecordSummary(
            id=r.id,
            patient_id=r.patient_id,
            patient_name=r.patient.name,
            diagnosis=r.diagnosis,
            admission_date=r.admission_date,
            discharge_date=r.discharge_date,
            status=r.status,
            updated_at=r.updated_at,
        )
        for r in db.scalars(stmt).all()
    ]


@router.get("/{record_id}", response_model=schemas.RecordOut)
def get_record(record_id: int, db: Session = Depends(get_db)):
    return get_record_or_404(record_id, db)


@router.put("/{record_id}", response_model=schemas.RecordOut)
def update_record(record_id: int, payload: schemas.RecordUpdate, db: Session = Depends(get_db)):
    record = get_record_or_404(record_id, db)
    _apply_fields(record, payload)
    _replace_treatment_items(record, payload.treatment_items)
    embeddings.refresh_record_embedding(record)
    db.commit()
    return get_record_or_404(record_id, db)


@router.delete("/{record_id}", status_code=204)
def delete_record(record_id: int, db: Session = Depends(get_db)):
    record = get_record_or_404(record_id, db)
    # Cascade deletes the Attachment rows, but never touches the files on
    # disk, so remove those first - otherwise a deleted record's lab
    # reports and scans silently stay behind in data/attachments.
    attachment_paths = [config.ATTACHMENTS_DIR / a.stored_name for a in record.attachments]
    db.delete(record)
    db.commit()
    for path in attachment_paths:
        path.unlink(missing_ok=True)


@router.get("/{record_id}/pdf")
def record_pdf(record_id: int, db: Session = Depends(get_db)):
    record = get_record_or_404(record_id, db)
    pdf_bytes = pdf_export.render_discharge_pdf(record)
    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", record.patient.name).strip("_") or "patient"
    filename = f"discharge_{safe_name}_{record.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
