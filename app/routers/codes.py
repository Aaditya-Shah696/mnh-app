"""ICD-10-CM code suggestions for the diagnosis field."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import auth, schemas
from ..database import get_db
from ..services import codes, embeddings

router = APIRouter(
    prefix="/api/codes", tags=["codes"], dependencies=[Depends(auth.current_user)]
)


def _status() -> schemas.CodeIndexStatus:
    try:
        code_list = codes.load()
    except codes.CodesUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return schemas.CodeIndexStatus(
        **codes.index.snapshot(), code_set=f"ICD-10-CM FY{code_list.year}",
        codes=len(code_list.titles),
    )


@router.get("/status", response_model=schemas.CodeIndexStatus)
def code_status():
    return _status()


@router.get("/suggest", response_model=schemas.CodeSuggestions)
def suggest_codes(
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=8, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Codes for diagnosis text or a typed code. A typed code always works;
    suggestions by meaning start once the phrase vectors are built (see
    status). No audit row: the query is diagnosis wording, not a record."""
    status = _status()
    try:
        items, _ = codes.suggest(db, q, limit=limit)
    except embeddings.EmbeddingUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return schemas.CodeSuggestions(
        status=status,
        items=[schemas.CodeSuggestion(code=s.code, title=s.title, matched=s.matched,
                                      score=s.score, exact=s.exact) for s in items],
    )
