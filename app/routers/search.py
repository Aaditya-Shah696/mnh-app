"""One search box over every live record: keyword and meaning combined."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from .. import auth, models, schemas
from ..audit import audit
from ..database import get_db
from ..services import search as search_service
from .records import _summary

router = APIRouter(
    prefix="/api/search", tags=["search"], dependencies=[Depends(auth.current_user)]
)


@router.get("", response_model=schemas.SearchOut)
def search_records(
    request: Request,
    q: str = Query(min_length=1, max_length=200),
    section: Literal["any", "diagnosis", "examination", "investigations", "course", "medicines"] = "any",
    limit: int = Query(default=20, ge=1, le=50),
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    """Records matching the words typed (FTS5, BM25) or their meaning (local
    embeddings), fused by reciprocal rank. Each hit says where it matched
    and carries a highlighted snippet. Soft-deleted records never appear.

    The search is audited as record.search with the ids returned and the
    section, never the query text: it can hold names or clinical detail."""
    try:
        result = search_service.search(db, q, section=section, limit=limit)
    except search_service.SearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    audit(db, "record.search", request=request, user=user,
          detail={"section": section, "semantic": result.semantic_used,
                  "results": [hit.record.id for hit in result.hits]})
    db.commit()
    return schemas.SearchOut(
        hits=[
            schemas.SearchHitOut(
                record=_summary(hit.record), score=hit.score, section=hit.section,
                snippet=[schemas.SnippetPart(**part) for part in hit.snippet],
                keyword=hit.keyword, similarity=hit.similarity,
            )
            for hit in result.hits
        ],
        semantic_used=result.semantic_used,
        note=result.note,
    )
