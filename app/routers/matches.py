from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import auth, config, models, schemas
from ..audit import audit
from ..database import get_db
from ..models import utcnow
from ..services import embeddings

router = APIRouter(
    prefix="/api/match", tags=["match"], dependencies=[Depends(auth.current_user)]
)


def _audit_match_views(
    db: Session, request: Request, user: models.User, record_ids: list[int],
) -> None:
    if not record_ids:
        return
    cutoff = utcnow() - timedelta(minutes=config.MATCH_VIEW_AUDIT_MINUTES)
    already = set(db.scalars(
        select(models.AuditLog.entity_id).where(
            models.AuditLog.user_id == user.id,
            models.AuditLog.action == "record.view",
            models.AuditLog.entity_type == "record",
            models.AuditLog.entity_id.in_(record_ids),
            models.AuditLog.ts >= cutoff,
        )
    ))
    for record_id in record_ids:
        if record_id not in already:
            audit(db, "record.view", request=request, user=user, entity_type="record",
                  entity_id=record_id, detail={"via": "similar_cases"})


def _match_record(record: models.DischargeRecord) -> schemas.MatchRecord:
    return schemas.MatchRecord(
        id=record.id,
        patient_id=record.patient_id,
        patient_name=record.patient.name,
        admission_date=record.admission_date,
        discharge_date=record.discharge_date,
        diagnosis=record.diagnosis,
        advice=record.advice,
        treatment_items=[
            schemas.TreatmentItemOut.model_validate(item)
            for item in record.treatment_items if item.category == "discharge"
        ],
    )


@router.post("", response_model=list[schemas.MatchResult])
def match_records(
    query: schemas.MatchQuery, request: Request,
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    """Top-N most similar past discharge records for in-progress form text.

    Similarity is cosine distance between local sentence embeddings of
    diagnosis + history + treatment text. If the embedding model cannot
    load, this fails loudly with 503; there is no degraded keyword-match
    fallback. Soft-deleted records are never candidates.
    """
    try:
        query_vec = embeddings.embed_text(query.text)
    except embeddings.EmbeddingUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        chosen = embeddings.rank_similar(
            db, query_vec, limit=query.limit, exclude_record_id=query.exclude_record_id,
        )
    except embeddings.EmbeddingMismatch as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not chosen:
        return []

    records = {
        record.id: record
        for record in db.scalars(
            select(models.DischargeRecord)
            .options(
                selectinload(models.DischargeRecord.treatment_items),
                selectinload(models.DischargeRecord.patient),
            )
            .where(models.DischargeRecord.id.in_([record_id for record_id, _ in chosen]))
        ).all()
    }
    shown = [(records[record_id], score) for record_id, score in chosen if record_id in records]
    _audit_match_views(db, request, user, [record.id for record, _ in shown])
    db.commit()
    return [
        schemas.MatchResult(score=score, record=_match_record(record))
        for record, score in shown
    ]
