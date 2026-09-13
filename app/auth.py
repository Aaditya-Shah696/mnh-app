"""Authentication: password hashing, server-side sessions, login throttling.

Design (see .docs/AUTH_SECURITY_DEPLOYMENT_PLAN.md):
- Argon2id via argon2-cffi. Unknown usernames are verified against a
  fixed dummy hash so timing does not reveal whether an account exists.
- Sessions are opaque random tokens; the cookie holds the raw token and
  the `sessions` table holds its SHA-256. Idle and absolute expiry, and
  revocation, are all enforced server-side.
- Account lockout is stored on the user row (survives restarts); the
  per-IP throttle is in-process, which is correct because the app runs
  exactly one worker.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from collections import deque
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from . import config, models
from .database import get_db
from .models import utcnow

logger = logging.getLogger(__name__)

_hasher = PasswordHasher()
# Verified on every failed lookup of a non-existent username so the response
# time matches a real password check. Never a valid password.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))

LOGIN_FAILED_DETAIL = "Incorrect username or password"
NOT_AUTHENTICATED_DETAIL = "Not authenticated"


# ---------- Passwords ----------

def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def validate_new_password(password: str, username: str) -> None:
    """Raises HTTPException(422) if the password is not acceptable."""
    if len(password) < config.PASSWORD_MIN_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at least {config.PASSWORD_MIN_LENGTH} characters",
        )
    if len(password) > config.PASSWORD_MAX_LENGTH:
        raise HTTPException(status_code=422, detail="Password is too long")
    if password.strip().lower() == username.strip().lower():
        raise HTTPException(status_code=422, detail="Password must not equal the username")


# ---------- Sessions ----------

def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def client_ip(request: Request) -> str | None:
    # uvicorn --proxy-headers rewrites request.client from X-Forwarded-For
    # when the proxy is in --forwarded-allow-ips, so this is the real IP.
    return request.client.host if request.client else None


def mint_session(db: Session, user: models.User, request: Request) -> str:
    raw = secrets.token_urlsafe(32)
    now = utcnow()
    session = models.UserSession(
        token_hash=_token_hash(raw),
        user_id=user.id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=config.SESSION_MAX_DAYS),
        ip=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:300] or None,
    )
    db.add(session)
    return raw


def set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=int(config.SESSION_MAX_DAYS * 86400),
        path="/",
        secure=config.COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=config.SESSION_COOKIE_NAME,
        path="/",
        secure=config.COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )


def revoke_session(session: models.UserSession) -> None:
    if session.revoked_at is None:
        session.revoked_at = utcnow()


def revoke_user_sessions(db: Session, user_id: int, keep_session_id: int | None = None) -> int:
    """Revoke every live session of a user (optionally keeping one). Returns count."""
    stmt = (
        update(models.UserSession)
        .where(
            models.UserSession.user_id == user_id,
            models.UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow())
    )
    if keep_session_id is not None:
        stmt = stmt.where(models.UserSession.id != keep_session_id)
    return db.execute(stmt).rowcount


def prune_sessions(db: Session) -> int:
    """Delete rows that can never authenticate again. Safe to run any time."""
    now = utcnow()
    idle_cutoff = now - timedelta(hours=config.SESSION_IDLE_HOURS)
    rows = db.query(models.UserSession).filter(
        (models.UserSession.revoked_at.is_not(None))
        | (models.UserSession.expires_at < now)
        | (models.UserSession.last_seen_at < idle_cutoff)
    ).delete(synchronize_session=False)
    return rows


def _load_session(db: Session, raw_token: str) -> models.UserSession | None:
    stmt = (
        select(models.UserSession)
        .options(joinedload(models.UserSession.user))
        .where(models.UserSession.token_hash == _token_hash(raw_token))
    )
    return db.scalars(stmt).first()


def session_is_live(session: models.UserSession, now=None) -> bool:
    now = now or utcnow()
    if session.revoked_at is not None:
        return False
    if session.expires_at <= now:
        return False
    if session.last_seen_at + timedelta(hours=config.SESSION_IDLE_HOURS) <= now:
        return False
    return True


def _unauthenticated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=NOT_AUTHENTICATED_DETAIL,
        headers={"WWW-Authenticate": "Cookie"},
    )


def current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    """FastAPI dependency: the logged-in, active user, or 401."""
    raw = request.cookies.get(config.SESSION_COOKIE_NAME)
    if not raw:
        raise _unauthenticated()
    session = _load_session(db, raw)
    if session is None:
        raise _unauthenticated()
    now = utcnow()
    if not session_is_live(session, now):
        raise _unauthenticated()
    user = session.user
    if user is None or not user.is_active:
        raise _unauthenticated()
    if (now - session.last_seen_at).total_seconds() >= config.SESSION_TOUCH_SECONDS:
        session.last_seen_at = now
        db.commit()
    request.state.user = user
    request.state.session = session
    return user


def require_admin(user: models.User = Depends(current_user)) -> models.User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


# ---------- Brute-force protection ----------

class _IpThrottle:
    """Sliding-window counter per IP, in-process. One worker, so this is exact."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, ip: str | None) -> bool:
        """Record an attempt; returns False if this IP is over the limit."""
        key = ip or "unknown"
        now = time.monotonic()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            # Keep the dict from growing with one-off scanners.
            if len(self._hits) > 10_000:
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    self._hits.pop(k, None)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_ip_throttle = _IpThrottle(config.LOGIN_IP_LIMIT, config.LOGIN_IP_WINDOW_SECONDS)


def is_locked(user: models.User, now=None) -> bool:
    now = now or utcnow()
    return user.locked_until is not None and user.locked_until > now


def register_login_failure(user: models.User) -> None:
    user.failed_logins = (user.failed_logins or 0) + 1
    over = user.failed_logins - config.LOGIN_LOCK_THRESHOLD
    if over >= 0:
        minutes = config.LOGIN_LOCK_BASE_MINUTES * (2 ** over)
        minutes = min(minutes, config.LOGIN_LOCK_MAX_HOURS * 60)
        user.locked_until = utcnow() + timedelta(minutes=minutes)


def register_login_success(user: models.User) -> None:
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = utcnow()


def unlock_user(user: models.User) -> None:
    user.failed_logins = 0
    user.locked_until = None


def dummy_verify() -> None:
    """Burn the same time a real verification would, for unknown usernames."""
    try:
        _hasher.verify(_DUMMY_HASH, "not-the-password")
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        pass


def _pruner_loop() -> None:
    from .database import SessionLocal

    while True:
        db = SessionLocal()
        try:
            removed = prune_sessions(db)
            db.commit()
            if removed:
                logger.info("Pruned %d dead sessions", removed)
        except Exception:  # noqa: BLE001
            logger.exception("Session pruning failed")
            db.rollback()
        finally:
            db.close()
        time.sleep(3600)


def start_session_pruner() -> None:
    threading.Thread(target=_pruner_loop, daemon=True).start()


def warn_if_insecure_config() -> None:
    if not config.COOKIE_SECURE:
        logger.warning(
            "DISCHARGE_COOKIE_SECURE=0: session cookies are NOT marked Secure. "
            "Only acceptable for local development."
        )
    if config.IS_PRODUCTION and not config.PUBLIC_ORIGIN:
        logger.warning(
            "DISCHARGE_PUBLIC_ORIGIN is not set in production; the CSRF check "
            "will rely on the Host header alone."
        )
