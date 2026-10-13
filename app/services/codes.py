"""ICD-10-CM diagnosis code suggestions.

The code list is app/data/icd10cm_<year>.tsv, built from CMS's public-domain
release by scripts/build_icd10cm.py: one title per billable code plus the
Alphabetic Index phrases and inclusion terms that point to it (93k phrases
for FY2027). Suggestions embed the diagnosis text and rank codes by their
best-matching phrase. On 24 labelled demo diagnoses this put the right code
first 16 times and in the top five 20 times, against 11 and 17 with code
titles alone.

The phrase vectors are derived data (~70 MB as float16) built once in a
background thread and cached under config.CODE_CACHE_DIR, keyed by model
and code-file hash: not in the database, not in backups. Until they are
ready, typing a code (e.g. "J18.9") still works.

Codes this clinic has already chosen get a small boost, so the codes the
doctor actually uses rise above lookalikes (e.g. lobar pneumonia J18.1 over
"malignant neoplasm of lower lobe").
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, models
from . import embeddings

logger = logging.getLogger(__name__)

BATCH = 256
# Score added per log(1 + times the clinic has used a code). Small: it
# re-orders near ties, it does not overrule a clearly better match.
USAGE_BOOST = 0.02
CHUNK_ROWS = 16384  # float16 -> float32 conversion per query, in chunks


class CodesUnavailable(RuntimeError):
    pass


# ---------- The code list ----------

@dataclass(frozen=True)
class CodeList:
    path: Path
    version: str                     # sha256 prefix of the file
    year: str
    titles: dict[str, str]           # code -> title
    codes: tuple[str, ...]           # code per index position
    position: dict[str, int]         # code -> index position
    phrase_texts: tuple[str, ...]    # every embedded phrase (titles included)
    phrase_owner: np.ndarray         # phrase -> code position
    phrase_kind: tuple[str, ...]


def code_file() -> Path:
    if config.ICD10_FILE:
        return Path(config.ICD10_FILE)
    files = sorted(config.ICD10_DATA_DIR.glob("icd10cm_*.tsv"))
    if not files:
        raise CodesUnavailable(f"No ICD-10-CM code file in {config.ICD10_DATA_DIR}")
    return files[-1]


@lru_cache(maxsize=2)
def _load(path: Path, mtime: float) -> CodeList:
    raw = path.read_bytes()
    titles: dict[str, str] = {}
    position: dict[str, int] = {}
    texts, owner, kinds = [], [], []
    for line_no, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] not in ("title", "index", "inclusion"):
            raise CodesUnavailable(f"{path.name} line {line_no} is not code<TAB>kind<TAB>text")
        code, kind, text = parts
        if kind == "title":
            position[code] = len(position)
            titles[code] = text
        elif code not in position:
            raise CodesUnavailable(f"{path.name} line {line_no}: phrase before its code title")
        texts.append(text)
        owner.append(position[code])
        kinds.append(kind)
    year = re.search(r"(\d{4})", path.name)
    return CodeList(
        path=path, version=hashlib.sha256(raw).hexdigest()[:16],
        year=year.group(1) if year else "", titles=titles, codes=tuple(position),
        position=position,
        phrase_texts=tuple(texts), phrase_owner=np.array(owner, dtype=np.int32),
        phrase_kind=tuple(kinds),
    )


def load() -> CodeList:
    path = code_file()
    return _load(path, path.stat().st_mtime)


_CODE_SHAPE = re.compile(r"^[A-Za-z][0-9A-Za-z]{2}(?:\.?[0-9A-Za-z]{1,4})?$")


def normalize(code: str) -> str:
    """'j189', 'J18.9', ' j18.9 ' -> 'J18.9'."""
    bare = re.sub(r"[\s.]", "", code or "").upper()
    return bare if len(bare) <= 3 else bare[:3] + "." + bare[3:]


def title(code: str) -> str | None:
    return load().titles.get(normalize(code))


def resolve(codes: list[str], limit: int) -> list[dict]:
    """Validate and normalise codes chosen on a record; returns
    [{"code", "title"}] in order, without duplicates. Raises ValueError
    naming any code that is not in the current list."""
    out, seen, unknown = [], set(), []
    titles = load().titles
    for raw in codes:
        code = normalize(raw)
        if code in seen:
            continue
        seen.add(code)
        if code not in titles:
            unknown.append(raw)
            continue
        out.append({"code": code, "title": titles[code]})
    if unknown:
        raise ValueError("Not ICD-10-CM codes: " + ", ".join(unknown))
    if len(out) > limit:
        raise ValueError(f"At most {limit} diagnosis codes per record")
    return out


# ---------- Phrase vectors ----------

class _PhraseIndex:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state = "not_started"     # not_started | building | ready | failed
        self.done = 0
        self.total = 0
        self.error: str | None = None
        self.matrix: np.ndarray | None = None
        self.version: str | None = None

    def snapshot(self) -> dict:
        return {"state": self.state, "done": self.done, "total": self.total, "error": self.error}


index = _PhraseIndex()


def cache_path(codes: CodeList) -> Path:
    model = re.sub(r"[^A-Za-z0-9]+", "-", config.EMBEDDING_MODEL).strip("-")
    return config.CODE_CACHE_DIR / f"icd10cm-{codes.year}-{codes.version}-{model}.f16.npy"


def build_index(pause: float = 0.0) -> None:
    """Load the cached phrase vectors, or embed every phrase and cache them.
    `pause` sleeps between batches so a background build leaves CPU for
    requests on the 2-vCPU VPS."""
    with index._lock:
        if index.state in ("building", "ready"):
            return
        index.state, index.error = "building", None
    try:
        codes = load()
        path = cache_path(codes)
        index.total = len(codes.phrase_texts)
        if path.exists():
            matrix = np.load(path, mmap_mode="r")
            if matrix.shape[0] == index.total:
                index.matrix, index.version, index.done = matrix, codes.version, index.total
                index.state = "ready"
                logger.info("ICD-10-CM suggestions ready (%d phrases, cached)", index.total)
                return
        started = time.monotonic()
        chunks = []
        for start in range(0, index.total, BATCH):
            chunks.append(embeddings.embed_texts(list(codes.phrase_texts[start:start + BATCH])).astype(np.float16))
            index.done = min(start + BATCH, index.total)
            if pause:
                time.sleep(pause)
        matrix = np.vstack(chunks)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        with tmp.open("wb") as fh:
            np.save(fh, matrix)
        os.replace(tmp, path)
        index.matrix, index.version = matrix, codes.version
        index.state = "ready"
        logger.info("ICD-10-CM suggestions ready: embedded %d phrases in %.0fs",
                    index.total, time.monotonic() - started)
    except Exception as exc:  # noqa: BLE001
        index.state, index.error = "failed", str(exc)
        logger.exception("Building ICD-10-CM suggestions failed")


def start_build_thread() -> None:
    threading.Thread(target=build_index, kwargs={"pause": config.CODE_BUILD_PAUSE},
                     daemon=True).start()


# ---------- Suggesting ----------

@dataclass
class Suggestion:
    code: str
    title: str
    matched: str | None   # the index phrase or synonym that matched, if not the title
    score: float
    exact: bool = False


def usage_counts(db: Session) -> Counter:
    counts: Counter = Counter()
    for value in db.scalars(
        select(models.DischargeRecord.diagnosis_codes).where(
            models.DischargeRecord.deleted_at.is_(None),
            models.DischargeRecord.diagnosis_codes.is_not(None),
        )
    ):
        for item in value if isinstance(value, list) else json.loads(value or "[]"):
            counts[item["code"]] += 1
    return counts


def _code_matches(codes: CodeList, query: str, limit: int) -> list[Suggestion]:
    """A typed code, exact first, then codes it is a prefix of."""
    if not _CODE_SHAPE.match(query.strip()):
        return []
    target = normalize(query)
    bare = target.replace(".", "")
    hits = []
    if target in codes.titles:
        hits.append(Suggestion(target, codes.titles[target], None, 1.0, exact=True))
    for code in codes.codes:
        if len(hits) >= limit:
            break
        if code != target and code.replace(".", "").startswith(bare):
            hits.append(Suggestion(code, codes.titles[code], None, 0.99, exact=True))
    return hits


def suggest(db: Session, query: str, limit: int = 8) -> tuple[list[Suggestion], dict]:
    """Codes for a diagnosis (or a typed code), best first, plus the index
    status so the UI can say when meaning-based suggestions are not ready."""
    codes = load()
    query = " ".join((query or "").split())
    out = _code_matches(codes, query, limit)
    status = index.snapshot()
    if len(out) >= limit or index.state != "ready" or index.version != codes.version:
        return out[:limit], status

    qvec = embeddings.embed_text(query)  # plain: measured better than the query prefix here
    best = np.full(len(codes.codes), -1.0, dtype=np.float32)
    best_phrase = np.zeros(len(codes.codes), dtype=np.int64)
    matrix = index.matrix
    for start in range(0, matrix.shape[0], CHUNK_ROWS):
        scores = np.asarray(matrix[start:start + CHUNK_ROWS], dtype=np.float32) @ qvec
        owners = codes.phrase_owner[start:start + CHUNK_ROWS]
        # Per code, keep the best phrase in this chunk.
        order = np.lexsort((scores, owners))
        last = np.r_[owners[order][1:] != owners[order][:-1], True]
        top_idx = order[last]
        top_owner = owners[top_idx]
        better = scores[top_idx] > best[top_owner]
        best[top_owner[better]] = scores[top_idx][better]
        best_phrase[top_owner[better]] = start + top_idx[better]

    boosted = best.copy()
    for code, n in usage_counts(db).items():
        pos = codes.position.get(code)
        if pos is not None:
            boosted[pos] += USAGE_BOOST * math.log1p(n)

    taken = {s.code for s in out}
    for pos in np.argsort(boosted)[::-1]:
        if len(out) >= limit:
            break
        code = codes.codes[int(pos)]
        if code in taken:
            continue
        phrase = int(best_phrase[pos])
        matched = codes.phrase_texts[phrase] if codes.phrase_kind[phrase] != "title" else None
        out.append(Suggestion(code, codes.titles[code], matched, float(boosted[pos])))
    return out, status
