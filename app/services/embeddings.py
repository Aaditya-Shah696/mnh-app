"""Local sentence embeddings: the vector store behind similar cases, AI
drafting and meaning-based search.

- fastembed (ONNX, fully local after a one-time model download), loaded
  lazily so startup and plain CRUD never wait on it.
- Every record is embedded per section (models.VECTOR_SECTIONS) into the
  record_vectors table. A section is re-embedded only when its text or the
  model changes (SHA-256 of the exact text embedded).
- Saving a record never fails because embedding failed. Vectors for text
  that changed are dropped rather than left describing the old text, and
  the backfill thread fills them in once the model is available.
- Queries run against an in-memory float32 matrix per section, rebuilt
  lazily after any commit that touched records or vectors. One process, so
  one index (the app runs exactly one worker).
- /api/match fails loudly if the model cannot load; there is deliberately
  no degraded keyword fallback there.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from collections import Counter
from itertools import chain

import numpy as np
from sqlalchemy import event, select
from sqlalchemy.orm import Session, selectinload

from .. import config, models

logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()


class EmbeddingUnavailable(RuntimeError):
    pass


class EmbeddingMismatch(RuntimeError):
    """Stored vectors do not match the current model's dimension."""


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


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed several texts in one model call; rows are float32 unit vectors."""
    model = _get_model()
    matrix = np.array(list(model.embed(texts)), dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def embed_text(text: str) -> np.ndarray:
    """Embed one text; returns a float32 unit vector."""
    return embed_texts([text])[0]


# BGE v1.5 models retrieve better when a short query (not a document) is
# prefixed with this instruction. On the demo records it lifted search MRR
# from 0.90 to 0.93. Record-to-record matching is symmetric and uses none.
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def embed_query(text: str) -> np.ndarray:
    """Embed a short search query (not a record) for retrieval."""
    return embed_text(QUERY_INSTRUCTION + text)


# ---------- What each section embeds ----------

def _get(obj, key):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def _clean(value) -> str:
    return (value or "").strip()


_EXAM_LABELS = (
    ("examination_findings", "General examination"),
    ("throat_findings", "Throat"),
    ("respiratory_system", "Respiratory system"),
    ("cvs_system", "CVS"),
    ("abdominal_exam", "Abdomen"),
    ("cns_system", "CNS"),
)
_SIGN_LABELS = (
    ("pallor", "pallor"), ("icterus", "icterus"), ("rash", "rash"),
    ("cyanosis", "cyanosis"), ("meningeal_signs", "meningeal signs"),
    ("dehydration_signs", "dehydration"),
)


def treatment_text(fields) -> str:
    return "; ".join(
        " ".join(p for p in (_get(t, "drug"), _get(t, "dose"),
                             _get(t, "frequency"), _get(t, "duration")) if p)
        for t in (_get(fields, "treatment_items") or [])
    )


def section_texts(fields) -> dict[str, str]:
    """The text embedded for each section. Works on a stored record or an
    in-progress form (pydantic model or dict). Empty sections are omitted."""
    summary = "\n".join(p for p in (
        _clean(_get(fields, "diagnosis")), _clean(_get(fields, "history")),
        treatment_text(fields).strip(),
    ) if p)

    exam_lines = [
        f"{label}: {_clean(_get(fields, key))}"
        for key, label in _EXAM_LABELS if _clean(_get(fields, key))
    ]
    present = [label for key, label in _SIGN_LABELS if _get(fields, key) == "yes"]
    if present:
        exam_lines.append("Signs present: " + ", ".join(present))

    texts = {
        "summary": summary,
        "examination": "\n".join(exam_lines),
        "investigations": _clean(_get(fields, "investigations")),
        "course": _clean(_get(fields, "course_in_hospital")),
    }
    return {section: text for section, text in texts.items() if text}


def record_text(record) -> str:
    """The summary text: what similar cases are matched on."""
    return section_texts(record).get("summary", "")


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------- Writing vectors ----------

def needs_refresh(record: models.DischargeRecord) -> bool:
    texts = section_texts(record)
    stored = {v.section: v for v in record.vectors}
    if set(stored) != set(texts):
        return True
    return any(
        v.model != config.EMBEDDING_MODEL or v.text_hash != text_hash(texts[s])
        for s, v in stored.items()
    )


def refresh_record_vectors(record: models.DischargeRecord) -> None:
    """Bring the record's section vectors in line with its text. Never
    raises: a failed embedding must not block saving patient data."""
    texts = section_texts(record)
    existing = {v.section: v for v in record.vectors}

    for section, vector in existing.items():
        if section not in texts:
            record.vectors.remove(vector)

    todo = []
    for section, text in texts.items():
        h = text_hash(text)
        current = existing.get(section)
        if current is not None and current.model == config.EMBEDDING_MODEL and current.text_hash == h:
            continue
        todo.append((section, text, h))
    if not todo:
        return

    try:
        matrix = embed_texts([text for _, text, _ in todo])
    except EmbeddingUnavailable as exc:
        logger.warning("Record %s saved WITHOUT embeddings for %s: %s",
                       record.id, ", ".join(s for s, _, _ in todo), exc)
        for section, _, _ in todo:
            current = existing.get(section)
            if current is not None:
                record.vectors.remove(current)  # never describe text that has changed
        return

    for (section, _, h), vec in zip(todo, matrix):
        current = existing.get(section)
        if current is None:
            record.vectors.append(models.RecordVector(
                section=section, model=config.EMBEDDING_MODEL, text_hash=h, vector=vec.tobytes(),
            ))
        else:
            current.model = config.EMBEDDING_MODEL
            current.text_hash = h
            current.vector = vec.tobytes()


def backfill_missing_vectors(batch_size: int = 50) -> int:
    """Embed sections that are missing, stale or from another model.
    Runs in a background thread at startup. Returns records refreshed."""
    from ..database import SessionLocal

    db = SessionLocal()
    count = 0
    try:
        ids = list(db.scalars(select(models.DischargeRecord.id).order_by(models.DischargeRecord.id)))
        for start in range(0, len(ids), batch_size):
            records = db.scalars(
                select(models.DischargeRecord)
                .options(selectinload(models.DischargeRecord.treatment_items),
                         selectinload(models.DischargeRecord.vectors))
                .where(models.DischargeRecord.id.in_(ids[start:start + batch_size]))
            ).all()
            touched = 0
            for record in records:
                if needs_refresh(record):
                    refresh_record_vectors(record)
                    touched += 1
            if touched:
                db.commit()
                count += touched
        if count:
            logger.info("Backfilled embeddings for %d records", count)
    except Exception:  # noqa: BLE001
        logger.exception("Embedding backfill failed")
        db.rollback()
    finally:
        db.close()
    return count


def start_backfill_thread() -> None:
    threading.Thread(target=backfill_missing_vectors, daemon=True).start()


# ---------- The in-memory index ----------

_EMPTY = (np.zeros(0, dtype=np.int64), np.zeros((0, 0), dtype=np.float32))


class _VectorIndex:
    """Per-section (ids, matrix) of live records, built from record_vectors
    on first use after any commit that changed records or vectors."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation = 0
        self._built = -1
        self._sections: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    def invalidate(self) -> None:
        with self._lock:
            self._generation += 1

    def get(self, db: Session, section: str) -> tuple[np.ndarray, np.ndarray]:
        with self._lock:
            if self._built != self._generation:
                self._sections = self._load(db)
                self._built = self._generation
            return self._sections.get(section, _EMPTY)

    @staticmethod
    def _load(db: Session) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        rows = db.execute(
            select(models.RecordVector.record_id, models.RecordVector.section,
                   models.RecordVector.vector)
            .join(models.DischargeRecord,
                  models.DischargeRecord.id == models.RecordVector.record_id)
            .where(models.DischargeRecord.deleted_at.is_(None),
                   models.RecordVector.model == config.EMBEDDING_MODEL)
            .order_by(models.RecordVector.record_id)
        ).all()
        grouped: dict[str, list] = {}
        for row in rows:
            grouped.setdefault(row.section, []).append(row)
        out = {}
        for section, section_rows in grouped.items():
            # A vector of another length (corrupt, or written by a different
            # model under the same name) is skipped, not allowed to break
            # every query.
            size = Counter(len(r.vector) for r in section_rows).most_common(1)[0][0]
            good = [r for r in section_rows if len(r.vector) == size]
            if len(good) != len(section_rows):
                logger.warning("Skipping %d %s vectors of unexpected size",
                               len(section_rows) - len(good), section)
            ids = np.array([r.record_id for r in good], dtype=np.int64)
            matrix = np.frombuffer(b"".join(r.vector for r in good), dtype=np.float32)
            out[section] = (ids, matrix.reshape(len(good), size // 4))
        return out


index = _VectorIndex()


@event.listens_for(Session, "after_flush")
def _note_vector_changes(session, flush_context) -> None:
    for obj in chain(session.new, session.dirty, session.deleted):
        if isinstance(obj, (models.DischargeRecord, models.RecordVector)):
            session.info["vectors_changed"] = True
            return


@event.listens_for(Session, "after_commit")
def _invalidate_after_commit(session) -> None:
    # After the commit, not the flush: a rebuild between the two would read
    # the old committed state and then be marked current.
    if session.info.pop("vectors_changed", False):
        index.invalidate()


@event.listens_for(Session, "after_rollback")
def _forget_after_rollback(session) -> None:
    session.info.pop("vectors_changed", None)


# ---------- Querying ----------

def _scores(db: Session, query_vec: np.ndarray, section: str):
    ids, matrix = index.get(db, section)
    if not len(ids):
        return ids, np.zeros(0, dtype=np.float32)
    if matrix.shape[1] != query_vec.shape[0]:
        raise EmbeddingMismatch(
            "Stored embeddings do not match the current model; re-save records."
        )
    return ids, matrix @ query_vec  # unit vectors, so dot product == cosine


def rank_similar(
    db: Session,
    query_vec: np.ndarray,
    *,
    limit: int,
    exclude_record_id: int | None = None,
    where=(),
    section: str = "summary",
) -> list[tuple[int, float]]:
    """Ids and cosine scores of the `limit` live records most similar to
    `query_vec` in one section, best first. `where` adds SQLAlchemy
    conditions on DischargeRecord (e.g. status == "final")."""
    ids, scores = _scores(db, query_vec, section)
    if not len(ids):
        return []
    mask = np.ones(len(ids), dtype=bool)
    if exclude_record_id is not None:
        mask &= ids != exclude_record_id
    if where:
        allowed = np.fromiter(
            db.scalars(select(models.DischargeRecord.id).where(*where)), dtype=np.int64,
        )
        mask &= np.isin(ids, allowed)
    candidates = np.flatnonzero(mask)
    order = candidates[np.argsort(scores[candidates])[::-1][:limit]]
    return [(int(ids[i]), float(scores[i])) for i in order]


def best_section_scores(
    db: Session, query_vec: np.ndarray, sections: tuple[str, ...],
) -> dict[int, tuple[float, str]]:
    """For each live record, its best cosine score across `sections` and
    the section that produced it."""
    best: dict[int, tuple[float, str]] = {}
    for section in sections:
        ids, scores = _scores(db, query_vec, section)
        for record_id, score in zip(ids.tolist(), scores.tolist()):
            if record_id not in best or score > best[record_id][0]:
                best[record_id] = (score, section)
    return best
