"""Admin-only audit log viewer."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth, models, schemas
from ..audit import ACTIONS, ENTITY_TYPES
from ..database import get_db

router = APIRouter(
    prefix="/api/audit", tags=["audit"], dependencies=[Depends(auth.require_admin)]
)


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
            conditions.append(models.AuditLog.action.like(action + "%"))
        else:
            conditions.append(models.AuditLog.action == action)
    if entity_type:
        conditions.append(models.AuditLog.entity_type == entity_type)
    if entity_id is not None:
        conditions.append(models.AuditLog.entity_id == entity_id)
    if since is not None:
        conditions.append(models.AuditLog.ts >= since.replace(tzinfo=None))
    if until is not None:
        conditions.append(models.AuditLog.ts <= until.replace(tzinfo=None))

    total = db.scalar(
        select(func.count()).select_from(models.AuditLog).where(*conditions)
    ) or 0
    rows = db.scalars(
        select(models.AuditLog)
        .where(*conditions)
        .order_by(models.AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return schemas.AuditPage(
        items=[schemas.AuditOut.model_validate(r) for r in rows],
        total=total, limit=limit, offset=offset,
    )
