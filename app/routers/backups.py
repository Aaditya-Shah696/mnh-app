from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import auth, models
from ..audit import audit
from ..database import get_db
from ..services import backup

router = APIRouter(
    prefix="/api/backup", tags=["backup"], dependencies=[Depends(auth.current_user)]
)


@router.get("/status")
def backup_status() -> dict:
    last = backup.last_backup_time()
    backups = backup.list_backups()
    return {
        "last_backup": last.isoformat(timespec="seconds") if last else None,
        "backup_count": len(backups),
        "latest_file": backups[-1].name if backups else None,
    }


@router.post("", status_code=201)
def run_backup(
    request: Request,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        path = backup.create_backup()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Backup failed: {exc}") from exc
    audit(db, "backup.create", request=request, user=admin, entity_type="backup",
          detail={"file": path.name, "size_bytes": path.stat().st_size})
    db.commit()
    return {"file": path.name, "size_bytes": path.stat().st_size}
