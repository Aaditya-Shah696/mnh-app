from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import config, models, schemas
from ..database import get_db
from .records import get_record_or_404

router = APIRouter(prefix="/api", tags=["attachments"])

_CHUNK = 1024 * 1024


@router.post(
    "/records/{record_id}/attachments",
    response_model=schemas.AttachmentOut,
    status_code=201,
)
async def upload_attachment(
    record_id: int, file: UploadFile, db: Session = Depends(get_db)
):
    get_record_or_404(record_id, db)

    if file.content_type not in config.ALLOWED_ATTACHMENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"File type '{file.content_type}' not allowed. "
            "Allowed: PDF, JPEG, PNG, WebP, Word documents.",
        )

    original_name = Path(file.filename or "file").name
    suffix = Path(original_name).suffix[:10]
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    dest = config.ATTACHMENTS_DIR / stored_name

    max_bytes = config.MAX_ATTACHMENT_MB * 1024 * 1024
    size = 0
    try:
        with open(dest, "wb") as out:
            while chunk := await file.read(_CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds {config.MAX_ATTACHMENT_MB} MB limit.",
                    )
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except OSError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not store file: {exc}") from exc

    attachment = models.Attachment(
        record_id=record_id,
        original_name=original_name,
        stored_name=stored_name,
        content_type=file.content_type,
        size_bytes=size,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


def _get_attachment_or_404(attachment_id: int, db: Session) -> models.Attachment:
    attachment = db.get(models.Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return attachment


@router.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: int, db: Session = Depends(get_db)):
    attachment = _get_attachment_or_404(attachment_id, db)
    path = config.ATTACHMENTS_DIR / attachment.stored_name
    if not path.exists():
        raise HTTPException(status_code=410, detail="Stored file is missing on disk")
    return FileResponse(
        path,
        media_type=attachment.content_type or "application/octet-stream",
        filename=attachment.original_name,
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: int, db: Session = Depends(get_db)):
    attachment = _get_attachment_or_404(attachment_id, db)
    path = config.ATTACHMENTS_DIR / attachment.stored_name
    db.delete(attachment)
    db.commit()
    path.unlink(missing_ok=True)
