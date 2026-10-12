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


def _locked(locked_until) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail=auth.locked_detail(locked_until),
        headers={"Retry-After": str(auth.retry_after_seconds(locked_until))},
    )


def _failure_detail(reason: str, failures: int | None, locked_until) -> dict:
    detail: dict = {"reason": reason}
    if failures is not None:
        detail["failed_logins"] = failures
    if locked_until is not None:
        detail["locked_until"] = locked_until.isoformat(timespec="seconds")
    return detail


@router.post("/login", response_model=schemas.UserOut)
def login(
    payload: schemas.LoginIn, request: Request, response: Response,
    db: Session = Depends(get_db),
):
    ip = auth.client_ip(request)
    if not auth.login_ip_throttle.check(ip):
        audit(db, "login.throttled", request=request, username=payload.username)
        db.commit()
        auth.log_rejected_login(ip)
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in attempts from this network. Wait ten minutes and try again.",
            headers={"Retry-After": "600"},
        )

    with auth.login_attempt_guard(payload.username, ip):
        user = db.scalars(
            select(models.User).where(models.User.username == payload.username)
        ).first()

        locked_until = auth.active_lock(db, payload.username, ip)
        if locked_until is not None:
            auth.dummy_verify()
            audit(db, "login.locked", request=request, user=user, username=payload.username)
            db.commit()
            auth.log_rejected_login(ip)
            raise _locked(locked_until)

        if user is None or not user.is_active:
            auth.dummy_verify()
            failures, locked_until = auth.register_login_failure(db, payload.username, ip, user)
            reason = "unknown_user" if user is None else "inactive"
            audit(db, "login.failure", request=request, user=user, username=payload.username,
                  detail=_failure_detail(reason, None, locked_until))
            db.commit()
            auth.log_rejected_login(ip)
            raise _failed()

        if not auth.verify_password(user.password_hash, payload.password):
            failures, locked_until = auth.register_login_failure(db, payload.username, ip, user)
            audit(db, "login.failure", request=request, user=user,
                  detail=_failure_detail("bad_password", failures, locked_until))
            db.commit()
            auth.log_rejected_login(ip)
            raise _failed()

        if auth.password_needs_rehash(user.password_hash):
            user.password_hash = auth.hash_password(payload.password)
        auth.register_login_success(db, user, ip)
        raw_token = auth.mint_session(db, user, request)
        audit(db, "login.success", request=request, user=user)
        db.commit()
    auth.set_session_cookie(response, raw_token)
    return user


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    session = getattr(request.state, "session", None)
    if session is not None:
        auth.revoke_session(session)
    audit(db, "logout", request=request, user=user)
    db.commit()
    result = Response(status_code=204)
    auth.clear_session_cookie(result)
    return result


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(auth.current_user)):
    return user


@router.post("/password", status_code=204)
def change_password(
    payload: schemas.PasswordChange, request: Request,
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    ip = auth.client_ip(request)
    with auth.login_attempt_guard(user.username, ip):
        locked_until = auth.active_lock(db, user.username, ip)
        if locked_until is not None:
            audit(db, "login.locked", request=request, user=user,
                  detail={"reason": "password_change"})
            db.commit()
            auth.log_rejected_login(ip)
            raise _locked(locked_until)
        if not auth.verify_password(user.password_hash, payload.current_password):
            failures, locked_until = auth.register_login_failure(db, user.username, ip, user)
            audit(db, "login.failure", request=request, user=user,
                  detail=_failure_detail("bad_current_password_on_change", failures, locked_until))
            db.commit()
            auth.log_rejected_login(ip)
            raise HTTPException(status_code=403, detail="Current password is incorrect")
        auth.validate_new_password(payload.new_password, user.username)
        auth.clear_login_failures(db, user, ip)
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
