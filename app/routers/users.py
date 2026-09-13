"""Admin-only user management. There is no self-registration."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth, models, schemas
from ..audit import audit
from ..database import get_db

router = APIRouter(
    prefix="/api/users", tags=["users"], dependencies=[Depends(auth.require_admin)]
)


def _get_user_or_404(user_id: int, db: Session) -> models.User:
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _active_admin_count(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(models.User).where(
            models.User.role == "admin", models.User.is_active.is_(True)
        )
    ) or 0


@router.get("", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(models.User).order_by(models.User.username)).all()


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(
    payload: schemas.UserCreate, request: Request,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    exists = db.scalars(
        select(models.User).where(models.User.username == payload.username)
    ).first()
    if exists is not None:
        raise HTTPException(status_code=409, detail="Username already exists")
    auth.validate_new_password(payload.password, payload.username)
    user = models.User(
        username=payload.username,
        display_name=payload.display_name,
        role=payload.role,
        password_hash=auth.hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    audit(db, "user.create", request=request, user=admin, entity_type="user",
          entity_id=user.id, detail={"username": user.username, "role": user.role})
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int, payload: schemas.UserUpdate, request: Request,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(user_id, db)
    changes: list[str] = []

    if payload.display_name is not None and payload.display_name != user.display_name:
        user.display_name = payload.display_name
        changes.append("display_name")

    if payload.role is not None and payload.role != user.role:
        if user.id == admin.id:
            raise HTTPException(status_code=409, detail="You cannot change your own role")
        if user.role == "admin" and user.is_active and _active_admin_count(db) <= 1:
            raise HTTPException(status_code=409, detail="Cannot demote the last administrator")
        user.role = payload.role
        changes.append("role")

    if payload.unlock:
        auth.unlock_user(user)
        audit(db, "user.unlock", request=request, user=admin, entity_type="user",
              entity_id=user.id, detail={"username": user.username})

    if payload.is_active is not None and payload.is_active != user.is_active:
        if user.id == admin.id:
            raise HTTPException(status_code=409, detail="You cannot deactivate yourself")
        if not payload.is_active and user.role == "admin" and _active_admin_count(db) <= 1:
            raise HTTPException(status_code=409, detail="Cannot deactivate the last administrator")
        user.is_active = payload.is_active
        if payload.is_active:
            audit(db, "user.activate", request=request, user=admin, entity_type="user",
                  entity_id=user.id, detail={"username": user.username})
        else:
            revoked = auth.revoke_user_sessions(db, user.id)
            audit(db, "user.deactivate", request=request, user=admin, entity_type="user",
                  entity_id=user.id,
                  detail={"username": user.username, "sessions_revoked": revoked})

    if changes:
        audit(db, "user.update", request=request, user=admin, entity_type="user",
              entity_id=user.id, detail={"username": user.username, "fields": changes})
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reset-password", status_code=204)
def reset_password(
    user_id: int, payload: schemas.PasswordReset, request: Request,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(user_id, db)
    auth.validate_new_password(payload.new_password, user.username)
    user.password_hash = auth.hash_password(payload.new_password)
    user.password_changed_at = models.utcnow()
    auth.unlock_user(user)
    keep = None
    if user.id == admin.id:
        session = getattr(request.state, "session", None)
        keep = session.id if session else None
    revoked = auth.revoke_user_sessions(db, user.id, keep_session_id=keep)
    audit(db, "user.reset_password", request=request, user=admin, entity_type="user",
          entity_id=user.id, detail={"username": user.username, "sessions_revoked": revoked})
    db.commit()
    return Response(status_code=204)
