from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth, models, schemas
from ..audit import audit
from ..database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _failed() -> HTTPException:
    return HTTPException(status_code=401, detail=auth.LOGIN_FAILED_DETAIL)


@router.post("/login", response_model=schemas.UserOut)
def login(
    payload: schemas.LoginIn, request: Request, response: Response,
    db: Session = Depends(get_db),
):
    ip = auth.client_ip(request)
    if not auth.login_ip_throttle.check(ip):
        audit(db, "login.throttled", request=request, username=payload.username)
        db.commit()
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts from this address. Try again later.",
            headers={"Retry-After": "600"},
        )

    user = db.scalars(
        select(models.User).where(models.User.username == payload.username)
    ).first()

    if user is None:
        auth.dummy_verify()
        audit(db, "login.failure", request=request, username=payload.username,
              detail={"reason": "unknown_user"})
        db.commit()
        raise _failed()

    if not user.is_active:
        auth.dummy_verify()
        audit(db, "login.failure", request=request, user=user, detail={"reason": "inactive"})
        db.commit()
        raise _failed()

    if auth.is_locked(user):
        auth.dummy_verify()
        audit(db, "login.locked", request=request, user=user)
        db.commit()
        raise _failed()

    if not auth.verify_password(user.password_hash, payload.password):
        auth.register_login_failure(user)
        detail = {"reason": "bad_password", "failed_logins": user.failed_logins}
        if auth.is_locked(user):
            detail["locked_until"] = user.locked_until.isoformat(timespec="seconds")
        audit(db, "login.failure", request=request, user=user, detail=detail)
        db.commit()
        raise _failed()

    if auth.password_needs_rehash(user.password_hash):
        user.password_hash = auth.hash_password(payload.password)
    auth.register_login_success(user)
    raw_token = auth.mint_session(db, user, request)
    audit(db, "login.success", request=request, user=user)
    db.commit()
    auth.set_session_cookie(response, raw_token)
    return user


@router.post("/logout", status_code=204)
def logout(
    request: Request, response: Response,
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    session = getattr(request.state, "session", None)
    if session is not None:
        auth.revoke_session(session)
    audit(db, "logout", request=request, user=user)
    db.commit()
    auth.clear_session_cookie(response)
    return Response(status_code=204)


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(auth.current_user)):
    return user


@router.post("/password", status_code=204)
def change_password(
    payload: schemas.PasswordChange, request: Request,
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    if not auth.verify_password(user.password_hash, payload.current_password):
        audit(db, "login.failure", request=request, user=user,
              detail={"reason": "bad_current_password_on_change"})
        db.commit()
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    auth.validate_new_password(payload.new_password, user.username)
    user.password_hash = auth.hash_password(payload.new_password)
    user.password_changed_at = models.utcnow()
    session = getattr(request.state, "session", None)
    revoked = auth.revoke_user_sessions(
        db, user.id, keep_session_id=session.id if session else None
    )
    audit(db, "password.change", request=request, user=user,
          entity_type="user", entity_id=user.id, detail={"sessions_revoked": revoked})
    db.commit()
    return Response(status_code=204)
