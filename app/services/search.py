"""Record search: keyword (SQLite FTS5, BM25) and meaning (local embeddings)
combined with reciprocal rank fusion.

The FTS5 table `record_search` is derived data, like a cache: the app creates
it at startup, re-indexes a record whenever a route changes its text, and
re-checks every row against a content hash at startup so anything written
outside the routes (seed scripts, restores) is picked up. Its rowid is the
record id. Soft-deleted records stay indexed and are filtered at query time,
so delete and restore need no index work.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from .. import config, models
from . import embeddings

logger = logging.getLogger(__name__)

# Highlight markers. Control characters cannot come from the form, and are
# stripped from indexed text anyway, so they cannot be spoofed.
HIT_START, HIT_END = "\x02", "\x03"

# Indexed columns, in table order (the table's first column is content_hash).
COLUMNS = (
    "patient_name", "diagnosis", "history", "examination",
    "investigations", "course", "medicines", "advice",
)
# BM25 weights per column, content_hash first (unindexed, weight 0).
_BM25_WEIGHTS = (0.0, 4.0, 4.0, 1.5, 1.0, 1.0, 1.0, 2.0, 0.7)

_CREATE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS record_search USING fts5("
    "content_hash UNINDEXED, " + ", ".join(COLUMNS) + ", "
    "tokenize = 'porter unicode61 remove_diacritics 2', prefix = '2 3')"
)

# What the section filter on the search box restricts to: FTS columns (None
# means all) and vector sections searched by meaning.
SECTION_FILTERS: dict[str, tuple[tuple[str, ...] | None, tuple[str, ...]]] = {
    # "any" searches meaning by the summary vector only: across all sections
    # the short ones (course, investigations) matched noise far more often.
    "any": (None, ("summary",)),
    "diagnosis": (("diagnosis", "history"), ("summary",)),
    "examination": (("examination",), ("examination",)),
    "investigations": (("investigations",), ("investigations",)),
    "course": (("course",), ("course",)),
    "medicines": (("medicines",), ()),
}
# Vector section -> the section name shown with a meaning-only hit.
_VECTOR_SECTION_LABEL = {
    "summary": "diagnosis", "examination": "examination",
    "investigations": "investigations", "course": "course",
}

RRF_K = 60
CANDIDATES = 50
MAX_QUERY_TOKENS = 12


class SearchUnavailable(RuntimeError):
    """SQLite was built without FTS5."""


# ---------- Building and maintaining the index ----------

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean(value) -> str:
    return _CONTROL.sub(" ", (value or "")).strip()


def _vitals(record) -> str:
    parts = [
        f"{label} {_clean(getattr(record, key, None))}"
        for key, label in (("temperature", "Temperature"), ("pulse", "Pulse"),
                           ("bp", "BP"), ("resp_rate", "RR"), ("spo2", "SpO2"))
        if _clean(getattr(record, key, None))
    ]
    return ", ".join(parts)


def document(record: models.DischargeRecord) -> dict[str, str]:
    """The text indexed for one record, by column."""
    exam = embeddings.section_texts(record).get("examination", "")
    vitals = _vitals(record)
    medicines = "\n".join(
        " ".join(p for p in (t.drug, t.dose, t.route, t.frequency, t.duration, t.instructions) if p)
        for t in record.treatment_items
    )
    doc = {
        "patient_name": record.patient.name if record.patient else "",
        "diagnosis": "\n".join(p for p in (
            record.diagnosis,
            "; ".join(f"{c['code']} {c['title']}" for c in (record.diagnosis_codes or [])),
        ) if p),
        "history": record.history,
        "examination": "\n".join(p for p in (exam, vitals) if p),
        "investigations": record.investigations,
        "course": record.course_in_hospital,
        "medicines": medicines,
        "advice": "\n".join(p for p in (record.advice, record.follow_up_notes) if p),
    }
    return {k: _clean(v) for k, v in doc.items()}


def _hash(doc: dict[str, str]) -> str:
    joined = "\x1f".join(doc[c] for c in COLUMNS)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def ensure_table(db: Session) -> None:
    try:
        db.execute(text(_CREATE))
    except Exception as exc:  # noqa: BLE001
        raise SearchUnavailable(f"Keyword search needs SQLite with FTS5: {exc}") from exc


def _write(db: Session, record: models.DischargeRecord) -> None:
    doc = document(record)
    db.execute(text("DELETE FROM record_search WHERE rowid = :id"), {"id": record.id})
    db.execute(
        text("INSERT INTO record_search (rowid, content_hash, " + ", ".join(COLUMNS) + ") "
             "VALUES (:id, :h, " + ", ".join(f":{c}" for c in COLUMNS) + ")"),
        {"id": record.id, "h": _hash(doc), **doc},
    )


def index_records(db: Session, record_ids) -> None:
    """Re-index records inside the caller's transaction. Call after a route
    changes a record's text, treatment items or patient name."""
    ids = sorted(set(record_ids))
    if not ids:
        return
    records = db.scalars(
        select(models.DischargeRecord)
        .options(selectinload(models.DischargeRecord.treatment_items),
                 selectinload(models.DischargeRecord.patient))
        .where(models.DischargeRecord.id.in_(ids))
    ).all()
    for record in records:
        _write(db, record)


def sync(db: Session) -> dict[str, int]:
    """Create the table if needed and make it match the records exactly:
    index missing or changed records, drop rows for records that no longer
    exist. Commits. Returns counts."""
    ensure_table(db)
    stored = dict(db.execute(text("SELECT rowid, content_hash FROM record_search")).all())
    records = db.scalars(
        select(models.DischargeRecord)
        .options(selectinload(models.DischargeRecord.treatment_items),
                 selectinload(models.DischargeRecord.patient))
    ).all()
    written = 0
    for record in records:
        if stored.get(record.id) != _hash(document(record)):
            _write(db, record)
            written += 1
    live = {r.id for r in records}
    orphans = [rowid for rowid in stored if rowid not in live]
    for rowid in orphans:
        db.execute(text("DELETE FROM record_search WHERE rowid = :id"), {"id": rowid})
    db.commit()
    if written or orphans:
        logger.info("Search index: %d records indexed, %d stale rows removed", written, len(orphans))
    return {"indexed": written, "removed": len(orphans)}


def sync_at_startup() -> None:
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        sync(db)
    except SearchUnavailable as exc:
        logger.error("%s", exc)
        db.rollback()
    finally:
        db.close()


# ---------- Querying ----------

def match_expression(query: str, columns: tuple[str, ...] | None) -> str | None:
    """A safe FTS5 query: every word becomes a quoted prefix term, all
    required. Operators, quotes and brackets typed by the user are inert."""
    tokens = re.findall(r"\w+", query or "", flags=re.UNICODE)[:MAX_QUERY_TOKENS]
    if not tokens:
        return None
    expr = " AND ".join(f'"{t}"*' for t in tokens)
    if columns:
        expr = "{" + " ".join(columns) + "} : (" + expr + ")"
    return expr


def segments(marked: str) -> list[dict]:
    """Split text carrying HIT_START/HIT_END markers into plain and
    highlighted runs, so the UI never has to parse or inject HTML."""
    out, pos = [], 0
    for m in re.finditer(re.escape(HIT_START) + "(.*?)" + re.escape(HIT_END), marked, flags=re.S):
        if m.start() > pos:
            out.append({"text": marked[pos:m.start()], "hit": False})
        out.append({"text": m.group(1), "hit": True})
        pos = m.end()
    if pos < len(marked):
        out.append({"text": marked[pos:], "hit": False})
    return [s for s in out if s["text"]]


@dataclass
class KeywordHit:
    record_id: int
    column: str
    snippet: str


def keyword_search(
    db: Session, query: str, columns: tuple[str, ...] | None, limit: int = CANDIDATES,
) -> list[KeywordHit]:
    expr = match_expression(query, columns)
    if expr is None:
        return []
    ensure_table(db)
    highlights = ", ".join(
        f"highlight(record_search, {i + 1}, :hs, :he) AS h{i}" for i in range(len(COLUMNS))
    )
    rows = db.execute(
        text(
            "SELECT record_search.rowid AS id, "
            f"snippet(record_search, -1, :hs, :he, ' … ', 16) AS snip, {highlights} "
            "FROM record_search JOIN discharge_records d ON d.id = record_search.rowid "
            "WHERE record_search MATCH :q AND d.deleted_at IS NULL "
            f"ORDER BY bm25(record_search, {', '.join(str(w) for w in _BM25_WEIGHTS)}) "
            "LIMIT :limit"
        ),
        {"q": expr, "hs": HIT_START, "he": HIT_END, "limit": limit},
    ).mappings().all()
    hits = []
    for row in rows:
        allowed = columns or COLUMNS
        column = next(
            (c for i, c in enumerate(COLUMNS) if c in allowed and HIT_START in (row[f"h{i}"] or "")),
            allowed[0],
        )
        hits.append(KeywordHit(row["id"], column, row["snip"] or ""))
    return hits


@dataclass
class SearchHit:
    record: models.DischargeRecord
    score: float
    section: str
    snippet: list[dict]
    keyword: bool
    similarity: float | None


@dataclass
class SearchResult:
    hits: list[SearchHit] = field(default_factory=list)
    semantic_used: bool = False
    note: str | None = None


def _excerpt(record: models.DischargeRecord, vector_section: str, limit: int = 200) -> str:
    texts = embeddings.section_texts(record)
    if vector_section == "summary":
        # The row already shows the diagnosis; the history says more.
        body = record.history or record.diagnosis or ""
    else:
        body = texts.get(vector_section, "")
    body = " ".join(body.split())
    if len(body) > limit:
        body = body[:limit].rsplit(" ", 1)[0] + " …"
    return body


def meaning_outliers(meaning: list[tuple[int, float, str]]) -> list[tuple[int, float]]:
    """The records whose similarity stands out from this query's scores over
    the whole corpus, best first. A query unrelated to every record yields a
    flat distribution and so no outliers, which a fixed cut-off cannot tell."""
    if len(meaning) < config.SEARCH_MIN_CORPUS:
        return []
    scores = [s for _, s, _ in meaning]
    mean = sum(scores) / len(scores)
    std = (sum((s - mean) ** 2 for s in scores) / len(scores)) ** 0.5
    if std == 0:
        return []
    return [
        (rid, s) for rid, s, _ in meaning
        if s >= config.SEARCH_MIN_SIMILARITY and (s - mean) / std >= config.SEARCH_MIN_ZSCORE
    ]


def search(db: Session, query: str, section: str = "any", limit: int = 20) -> SearchResult:
    """Hybrid search over live records.

    1. Records containing the typed words (FTS5), ordered by reciprocal rank
       fusion of their BM25 rank and their meaning rank, so the word matches
       closest in meaning come first.
    2. Then up to SEARCH_MAX_MEANING_HITS records related only by meaning
       that stand out from the rest (see meaning_outliers).

    If the embedding model is unavailable the result says so in `note`
    instead of silently returning word matches alone."""
    columns, vector_sections = SECTION_FILTERS[section]
    result = SearchResult()
    query = (query or "").strip()

    keyword = keyword_search(db, query, columns)
    keyword_by_id = {h.record_id: h for h in keyword}

    meaning: list[tuple[int, float, str]] = []  # every live record, best first
    if vector_sections and len(query) >= config.SEARCH_SEMANTIC_MIN_CHARS:
        try:
            best = embeddings.best_section_scores(db, embeddings.embed_query(query), vector_sections)
            meaning = sorted(((rid, s, sec) for rid, (s, sec) in best.items()),
                             key=lambda item: item[1], reverse=True)
            result.semantic_used = True
        except (embeddings.EmbeddingUnavailable, embeddings.EmbeddingMismatch) as exc:
            logger.warning("Search by meaning unavailable: %s", exc)
            result.note = f"Showing word matches only; search by meaning is unavailable ({exc})."
    meaning_rank = {rid: i for i, (rid, _, _) in enumerate(meaning)}
    meaning_by_id = {rid: (s, sec) for rid, s, sec in meaning}

    def fused(rid: int, keyword_rank: int) -> float:
        score = 1.0 / (RRF_K + keyword_rank + 1)
        if rid in meaning_rank:
            score += 1.0 / (RRF_K + meaning_rank[rid] + 1)
        return score

    order = sorted(
        ((h.record_id, fused(h.record_id, i), True) for i, h in enumerate(keyword)),
        key=lambda item: item[1], reverse=True,
    )
    order += [
        (rid, s, False) for rid, s in meaning_outliers(meaning) if rid not in keyword_by_id
    ][:config.SEARCH_MAX_MEANING_HITS]
    order = order[:limit]
    if not order:
        return result

    records = {
        r.id: r for r in db.scalars(
            select(models.DischargeRecord)
            .options(selectinload(models.DischargeRecord.patient),
                     selectinload(models.DischargeRecord.treatment_items))
            .where(models.DischargeRecord.id.in_([rid for rid, _, _ in order]),
                   models.DischargeRecord.deleted_at.is_(None))
        )
    }
    for rid, score, is_keyword in order:
        record = records.get(rid)
        if record is None:
            continue
        similarity = meaning_by_id.get(rid, (None, None))[0]
        if is_keyword:
            hit = keyword_by_id[rid]
            section_name, snippet = hit.column, segments(hit.snippet)
        else:
            vector_section = meaning_by_id[rid][1]
            section_name = _VECTOR_SECTION_LABEL[vector_section]
            excerpt = _excerpt(record, vector_section)
            snippet = [{"text": excerpt, "hit": False}] if excerpt else []
        result.hits.append(SearchHit(
            record=record, score=score, section=section_name, snippet=snippet,
            keyword=is_keyword, similarity=similarity,
        ))
    return result
