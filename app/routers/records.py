from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import auth, config, models, schemas
from ..audit import audit, changed_fields
from ..database import get_db
from ..models import utcnow
from ..querying import contains_pattern
from ..services import codes, embeddings, pdf_export, search
from .patients import get_patient_or_404

router = APIRouter(
    prefix="/api/records", tags=["records"], dependencies=[Depends(auth.current_user)]
)


def get_record_or_404(
    record_id: int, db: Session, *, include_deleted: bool = False
) -> models.DischargeRecord:
    record = db.get(
        models.DischargeRecord,
        record_id,
        options=[
            selectinload(models.DischargeRecord.treatment_items),
            selectinload(models.DischargeRecord.patient),
        ],
    )
    if record is None or (record.deleted_at is not None and not include_deleted):
        raise HTTPException(status_code=404, detail="Record not found")
    return record


def _apply_fields(record: models.DischargeRecord, fields: schemas.RecordFields) -> list[str]:
    """Set the scalar fields and diagnosis codes; returns the names of the
    ones that changed. Unknown codes are a 422."""
    after = fields.model_dump(exclude={"treatment_items", "patient_id", "diagnosis_codes"})
    try:
        after["diagnosis_codes"] = codes.resolve(
            [c.code for c in fields.diagnosis_codes], limit=config.MAX_DIAGNOSIS_CODES,
        ) or None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    before = {k: getattr(record, k) for k in after}
    for key, value in after.items():
        setattr(record, key, value)
    return changed_fields(before, after)


def _replace_treatment_items(
    record: models.DischargeRecord, items: list[schemas.TreatmentItemIn]
) -> None:
    record.treatment_items.clear()
    for i, item in enumerate(items):
        data = item.model_dump()
        data["position"] = i
        record.treatment_items.append(models.TreatmentItem(**data))


def _summary(r: models.DischargeRecord) -> schemas.RecordSummary:
    return schemas.RecordSummary(
        id=r.id,
        patient_id=r.patient_id,
        patient_name=r.patient.name,
        diagnosis=r.diagnosis,
        admission_date=r.admission_date,
        discharge_date=r.discharge_date,
        status=r.status,
        deleted_at=r.deleted_at,
        updated_at=r.updated_at,
    )


@router.post("", response_model=schemas.RecordOut, status_code=201)
def create_record(
    payload: schemas.RecordCreate, request: Request,
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    get_patient_or_404(payload.patient_id, db)
    record = models.DischargeRecord(
        patient_id=payload.patient_id, created_by=user.id, updated_by=user.id
    )
    _apply_fields(record, payload)
    _replace_treatment_items(record, payload.treatment_items)
    db.add(record)
    db.flush()
    embeddings.refresh_record_vectors(record)
    search.index_records(db, [record.id])
    audit(db, "record.create", request=request, user=user, entity_type="record",
          entity_id=record.id,
          detail={"patient_id": record.patient_id, "status": record.status,
                  "treatment_items": len(record.treatment_items)})
    db.commit()
    return get_record_or_404(record.id, db)


@router.post("/duplicate-check", response_model=schemas.DuplicateCheckOut)
def duplicate_check(payload: schemas.DuplicateCheck, db: Session = Depends(get_db)):
    """Advisory check before saving a new record: does this patient already
    have a live record admitted the same day, or a near-identical one
    admitted within config.DUPLICATE_WINDOW_DAYS? Catches double entry from
    two devices or a half-saved draft. Nothing is blocked server-side."""
    patient = get_patient_or_404(payload.patient_id, db)
    others = {r.id: r for r in patient.active_records if r.id != payload.record_id}
    found: dict[int, dict] = {}
    admitted = payload.admission_date

    if admitted is not None:
        for r in others.values():
            if r.admission_date is not None and r.admission_date.date() == admitted.date():
                found[r.id] = {"reasons": ["same_admission_date"], "similarity": None}

    note = None
    summary = embeddings.section_texts(payload).get("summary")
    if summary and others:
        try:
            ranked = embeddings.rank_similar(
                db, embeddings.embed_text(summary), limit=len(others),
                exclude_record_id=payload.record_id,
                where=(models.DischargeRecord.patient_id == patient.id,),
            )
        except (embeddings.EmbeddingUnavailable, embeddings.EmbeddingMismatch) as exc:
            ranked = []
            note = f"Content comparison unavailable: {exc}"
        for record_id, score in ranked:
            if score < config.DUPLICATE_SIMILARITY or record_id not in others:
                continue
            r = others[record_id]
            if (admitted is not None and r.admission_date is not None
                    and abs((admitted - r.admission_date).days) > config.DUPLICATE_WINDOW_DAYS):
                continue
            entry = found.setdefault(record_id, {"reasons": [], "similarity": None})
            entry["reasons"].append("near_identical")
            entry["similarity"] = score

    candidates = [
        schemas.DuplicateCandidate(record=_summary(others[rid]), **info)
        for rid, info in sorted(found.items(), key=lambda kv: -(kv[1]["similarity"] or 1.0))
    ]
    return schemas.DuplicateCheckOut(candidates=candidates, note=note)


@router.get("", response_model=list[schemas.RecordSummary])
def list_records(
    q: str | None = Query(default=None, description="Filter by patient name"),
    limit: int = Query(default=30, ge=1, le=200),
    deleted: bool = Query(default=False, description="Admin only: list deleted records"),
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    if deleted and not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    visibility = (
        models.DischargeRecord.deleted_at.is_not(None)
        if deleted else models.DischargeRecord.deleted_at.is_(None)
    )
    stmt = (
        select(models.DischargeRecord)
        .options(selectinload(models.DischargeRecord.patient))
        .where(visibility)
        .order_by(models.DischargeRecord.updated_at.desc())
        .limit(limit)
    )
    if q:
        like = contains_pattern(q.strip())
        stmt = stmt.join(models.DischargeRecord.patient).where(
            models.Patient.name.ilike(like, escape="\\")
        )
    return [_summary(r) for r in db.scalars(stmt).all()]


@router.get("/{record_id}", response_model=schemas.RecordOut)
def get_record(
    record_id: int, request: Request,
    include_deleted: bool = Query(default=False),
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    if include_deleted and not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    record = get_record_or_404(record_id, db, include_deleted=include_deleted)
    audit(db, "record.view", request=request, user=user,
          entity_type="record", entity_id=record.id)
    db.commit()
    return record


@router.put("/{record_id}", response_model=schemas.RecordOut)
def update_record(
    record_id: int, payload: schemas.RecordUpdate, request: Request,
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    record = get_record_or_404(record_id, db)
    previous_status = record.status
    changed = _apply_fields(record, payload)
    _replace_treatment_items(record, payload.treatment_items)
    record.updated_by = user.id
    embeddings.refresh_record_vectors(record)
    db.flush()
    search.index_records(db, [record.id])
    audit(db, "record.update", request=request, user=user, entity_type="record",
          entity_id=record.id,
          detail={"fields": changed, "treatment_items": len(record.treatment_items)})
    if previous_status != "final" and record.status == "final":
        audit(db, "record.finalize", request=request, user=user,
              entity_type="record", entity_id=record.id)
    db.commit()
    return get_record_or_404(record_id, db)


@router.delete("/{record_id}", status_code=204)
def delete_record(
    record_id: int, request: Request,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    """Soft delete: the row stays, hidden from lists and the matcher, restorable."""
    record = get_record_or_404(record_id, db)
    record.deleted_at = utcnow()
    audit(db, "record.delete", request=request, user=admin, entity_type="record",
          entity_id=record.id, detail={"patient_id": record.patient_id})
    db.commit()


@router.post("/{record_id}/restore", response_model=schemas.RecordOut)
def restore_record(
    record_id: int, request: Request,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    record = get_record_or_404(record_id, db, include_deleted=True)
    if record.deleted_at is None:
        raise HTTPException(status_code=409, detail="Record is not deleted")
    record.deleted_at = None
    detail: dict = {"patient_id": record.patient_id}
    if record.patient.deleted_at is not None:
        record.patient.deleted_at = None
        detail["patient_restored"] = True
    audit(db, "record.restore", request=request, user=admin, entity_type="record",
          entity_id=record.id, detail=detail)
    db.commit()
    return get_record_or_404(record_id, db)


@router.get("/{record_id}/pdf")
def record_pdf(
    record_id: int, request: Request,
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    record = get_record_or_404(record_id, db)
    pdf_bytes = pdf_export.render_discharge_pdf(record)
    audit(db, "record.pdf", request=request, user=user,
          entity_type="record", entity_id=record.id)
    db.commit()
    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", record.patient.name).strip("_") or "patient"
    filename = f"discharge_{safe_name}_{record.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
