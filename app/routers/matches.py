from __future__ import annotations

from datetime import timedelta

import numpy as np
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

    stmt = select(
        models.DischargeRecord.id, models.DischargeRecord.embedding
    ).where(
        models.DischargeRecord.embedding.is_not(None),
        models.DischargeRecord.embedding_model == config.EMBEDDING_MODEL,
        models.DischargeRecord.deleted_at.is_(None),
    )
    if query.exclude_record_id is not None:
        stmt = stmt.where(models.DischargeRecord.id != query.exclude_record_id)

    rows = db.execute(stmt).all()
    if not rows:
        return []

    ids = [row.id for row in rows]
    matrix = np.frombuffer(b"".join(row.embedding for row in rows), dtype=np.float32)
    matrix = matrix.reshape(len(ids), -1)
    if matrix.shape[1] != query_vec.shape[0]:
        raise HTTPException(
            status_code=503,
            detail="Stored embeddings do not match the current model; re-save records.",
        )

    scores = matrix @ query_vec  # unit vectors, so dot product == cosine
    order = np.argsort(scores)[::-1][: query.limit]
    chosen = [(ids[int(idx)], float(scores[int(idx)])) for idx in order]

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
