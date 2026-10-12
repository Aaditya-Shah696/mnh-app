"""Admin-only audit log viewer."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import auth, models, schemas
from ..audit import ACTIONS, ENTITY_TYPES
from ..database import get_db
from ..querying import escape_like

router = APIRouter(
    prefix="/api/audit", tags=["audit"], dependencies=[Depends(auth.require_admin)]
)


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("/actions")
def list_actions() -> dict:
    return {"actions": list(ACTIONS), "entity_types": list(ENTITY_TYPES)}


@router.get("", response_model=schemas.AuditPage)
def list_audit(
    username: str | None = Query(default=None, max_length=50),
    user_id: int | None = None,
    action: str | None = Query(default=None, max_length=40),
    entity_type: str | None = Query(default=None, max_length=20),
    entity_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    before_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    conditions = []
    if username:
        conditions.append(models.AuditLog.username == username.strip().lower())
    if user_id is not None:
        conditions.append(models.AuditLog.user_id == user_id)
    if action:
        if action.endswith("."):
            prefix = action[:-1]
            conditions.append(or_(
                models.AuditLog.action == prefix,
                models.AuditLog.action.like(escape_like(action) + "%", escape="\\"),
            ))
        else:
            conditions.append(models.AuditLog.action == action)
    if entity_type:
        conditions.append(models.AuditLog.entity_type == entity_type)
    if entity_id is not None:
        conditions.append(models.AuditLog.entity_id == entity_id)
    if since is not None:
        conditions.append(models.AuditLog.ts >= _as_naive_utc(since))
    if until is not None:
        conditions.append(models.AuditLog.ts <= _as_naive_utc(until))

    total = db.scalar(
        select(func.count()).select_from(models.AuditLog).where(*conditions)
    ) or 0
    page_conditions = list(conditions)
    if before_id is not None:
        page_conditions.append(models.AuditLog.id < before_id)
    rows = db.scalars(
        select(models.AuditLog)
        .where(*page_conditions)
        .order_by(models.AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    next_before_id = None
    if rows:
        more = db.scalar(
            select(models.AuditLog.id)
            .where(*conditions, models.AuditLog.id < rows[-1].id)
            .limit(1)
        )
        if more is not None:
            next_before_id = rows[-1].id
    return schemas.AuditPage(
        items=[schemas.AuditOut.model_validate(r) for r in rows],
        total=total, limit=limit, offset=offset, next_before_id=next_before_id,
    )
