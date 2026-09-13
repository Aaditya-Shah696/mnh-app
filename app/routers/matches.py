from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth, config, models, schemas
from ..database import get_db
from ..services import embeddings
from .records import get_record_or_404

router = APIRouter(
    prefix="/api/match", tags=["match"], dependencies=[Depends(auth.current_user)]
)


@router.post("", response_model=list[schemas.MatchResult])
def match_records(query: schemas.MatchQuery, db: Session = Depends(get_db)):
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

    results = []
    for idx in order:
        record = get_record_or_404(ids[int(idx)], db)
        results.append(
            schemas.MatchResult(
                score=float(scores[int(idx)]),
                record=schemas.RecordOut.model_validate(record),
            )
        )
    return results
