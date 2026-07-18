"""Local sentence-embedding service for the similar-record recommender.

Uses fastembed (ONNX, fully local after a one-time model download).
The model is loaded lazily on first use so app startup and plain CRUD
never wait on it. Saving a record must never fail because embedding
failed; the record is saved with a NULL embedding and backfilled later.
The /api/match endpoint, by contrast, fails loudly if the model is
unavailable. There is deliberately no degraded text-match fallback.
"""
from __future__ import annotations

import logging
import threading

import numpy as np

from .. import config, models

logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()


class EmbeddingUnavailable(RuntimeError):
    pass


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                try:
                    from fastembed import TextEmbedding

                    logger.info("Loading embedding model %s", config.EMBEDDING_MODEL)
                    _model = TextEmbedding(model_name=config.EMBEDDING_MODEL)
                except Exception as exc:  # noqa: BLE001
                    raise EmbeddingUnavailable(
                        f"Embedding model '{config.EMBEDDING_MODEL}' could not be loaded: {exc}"
                    ) from exc
    return _model


def embed_text(text: str) -> np.ndarray:
    """Embed one text; returns a float32 unit vector."""
    model = _get_model()
    vec = np.array(next(iter(model.embed([text]))), dtype=np.float32)
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return vec


def record_text(record: models.DischargeRecord) -> str:
    """Canonical text a record is matched on: diagnosis, complaints, history, treatment."""
    treatment = "; ".join(
        " ".join(
            part
            for part in (t.drug, t.dose, t.frequency, t.duration)
            if part
        )
        for t in record.treatment_items
    )
    parts = [
        record.diagnosis or "",
        record.presenting_complaints or "",
        record.history or "",
        treatment,
    ]
    return "\n".join(p.strip() for p in parts if p.strip())


def refresh_record_embedding(record: models.DischargeRecord) -> None:
    """Compute and store the record's embedding. Never raises: a failed
    embedding must not block saving patient data."""
    text = record_text(record)
    if not text:
        record.embedding = None
        record.embedding_model = None
        return
    try:
        vec = embed_text(text)
        record.embedding = vec.tobytes()
        record.embedding_model = config.EMBEDDING_MODEL
    except EmbeddingUnavailable as exc:
        logger.warning("Record %s saved WITHOUT embedding: %s", record.id, exc)
        record.embedding = None
        record.embedding_model = None


def backfill_missing_embeddings() -> int:
    """Embed any records saved while the model was unavailable.
    Runs in a background thread at startup. Returns count backfilled."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from ..database import SessionLocal

    db = SessionLocal()
    count = 0
    try:
        stmt = (
            select(models.DischargeRecord)
            .options(selectinload(models.DischargeRecord.treatment_items))
            .where(models.DischargeRecord.embedding.is_(None))
        )
        for record in db.scalars(stmt).all():
            if not record_text(record):
                continue
            before = record.embedding
            refresh_record_embedding(record)
            if record.embedding is not None and before is None:
                count += 1
        if count:
            db.commit()
            logger.info("Backfilled embeddings for %d records", count)
    except Exception:  # noqa: BLE001
        logger.exception("Embedding backfill failed")
        db.rollback()
    finally:
        db.close()
    return count


def start_backfill_thread() -> None:
    threading.Thread(target=backfill_missing_embeddings, daemon=True).start()
