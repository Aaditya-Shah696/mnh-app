"""Append-only audit trail.

`audit()` adds a row to the *caller's* session without committing, so the
row lands in the same transaction as the change it describes: a record
edit without its audit row cannot happen. Details carry field NAMES and
state transitions, never clinical values.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from . import models
from .auth import client_ip

ACTIONS = (
    "login.success", "login.failure", "login.locked", "login.throttled", "logout",
    "password.change",
    "patient.create", "patient.update", "patient.view", "patient.delete", "patient.restore",
    "record.create", "record.update", "record.finalize", "record.view", "record.pdf",
    "record.delete", "record.restore",
    "backup.create",
    "user.create", "user.update", "user.deactivate", "user.activate",
    "user.unlock", "user.reset_password",
)

ENTITY_TYPES = ("patient", "record", "user", "backup")


def audit(
    db: Session,
    action: str,
    *,
    request: Request | None = None,
    user: models.User | None = None,
    username: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> models.AuditLog:
    if action not in ACTIONS:
        raise ValueError(f"Unknown audit action {action!r}")
    if entity_type is not None and entity_type not in ENTITY_TYPES:
        raise ValueError(f"Unknown entity type {entity_type!r}")
    if user is None and request is not None:
        user = getattr(request.state, "user", None)
    row = models.AuditLog(
        user_id=user.id if user else None,
        username=(user.username if user else username),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip=client_ip(request) if request is not None else None,
        detail=json.dumps(detail, separators=(",", ":"), sort_keys=True) if detail else None,
    )
    db.add(row)
    return row


def changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Names of keys whose value differs. Values themselves are never logged."""
    return sorted(k for k in after if before.get(k) != after.get(k))
