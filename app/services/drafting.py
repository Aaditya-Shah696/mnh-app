"""AI drafting of the "Course in hospital" section, retrieval-augmented.

Flow: the in-progress form -> local embedding search for the most similar
finalised past records -> strip identifiers from everything -> Claude drafts
the section from the CURRENT record's facts only, using the past cases as
examples of this doctor's style -> the doctor reviews the draft and decides
whether to insert it. This module never saves anything.

Fails loudly: when drafting is switched off or has no API key, callers get
DraftingUnavailable. There is no template or canned-text fallback.

Privacy: the model never receives a patient name, date of birth, IPD number,
calendar date or phone number. The current patient's name (and each past
case's own patient's name) is scrubbed from free text before sending.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import config, models
from . import embeddings

logger = logging.getLogger(__name__)

# Upper bound on what one request may send, a brake on cost and on pasted
# junk. A full discharge record is a few thousand characters.
MAX_INPUT_CHARS = 30_000
# Exemplar course text longer than this is trimmed; it is a style sample.
EXEMPLAR_COURSE_CHARS = 1_500

# Server-side refusal fallback (Claude API). Haiku has none, so the
# parameter is only sent to models that accept it.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class DraftingUnavailable(RuntimeError):
    """Drafting is switched off or not configured (no API key)."""


class DraftingFailed(RuntimeError):
    """The API call failed or returned no usable draft."""


class DraftInputTooLong(DraftingFailed):
    """The record is over MAX_INPUT_CHARS; nothing was sent."""


class DraftDeclined(RuntimeError):
    """The model declined the request (stop_reason == "refusal")."""


class CourseDraft(BaseModel):
    """Structured output the model must return."""

    course_in_hospital: str = Field(
        description="The drafted section: plain clinical prose, no headings."
    )
    missing_information: list[str] = Field(
        description=(
            "Short questions for the doctor about facts a course-in-hospital "
            "section usually states but this record does not."
        )
    )


@dataclass
class DraftStatus:
    enabled: bool
    model: str | None
    reason: str | None


@dataclass
class DraftContext:
    """Everything needed for one request, already de-identified."""

    record_text: str
    exemplars: list[tuple[int, str]]  # (record id, de-identified text)
    exemplar_note: str | None = None


@dataclass
class DraftResult:
    course_in_hospital: str
    missing_information: list[str]
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    exemplar_ids: list[int] = field(default_factory=list)


# ---------- Configuration ----------

def _key_from_file() -> str | None:
    try:
        key = config.ANTHROPIC_KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return key or None


def _api_key() -> str | None:
    """The environment wins; otherwise the key file. Never logged."""
    return os.environ.get("ANTHROPIC_API_KEY") or _key_from_file()


def _api_key_present() -> bool:
    return bool(_api_key() or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def status() -> DraftStatus:
    if not config.LLM_ENABLED:
        return DraftStatus(False, None, "AI drafting is switched off (DISCHARGE_LLM_ENABLED).")
    if not _api_key_present():
        return DraftStatus(
            False, None,
            "AI drafting is on but no API key is set (ANTHROPIC_API_KEY or "
            f"{config.ANTHROPIC_KEY_FILE.name}).",
        )
    return DraftStatus(True, config.LLM_MODEL, None)


_client = None
_client_lock = threading.Lock()


def _get_client():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                import anthropic

                key = _api_key()
                _client = anthropic.Anthropic(
                    **({"api_key": key} if key else {}),  # else ANTHROPIC_AUTH_TOKEN
                    timeout=config.LLM_TIMEOUT_SECONDS, max_retries=2,
                )
    return _client


def _fallback_kwargs(model: str) -> dict:
    if model.startswith("claude-haiku"):
        return {}
    return {"betas": [_FALLBACK_BETA], "fallbacks": "default"}


# ---------- De-identification ----------

_PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
_DATE = re.compile(
    r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b"            # 12/07/2026, 12-7-26
    r"|\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?\b"  # 2026-07-12[T10:00]
)
_REPEATED_CHILD = re.compile(r"\bthe child(?:\s+the child)+\b", re.IGNORECASE)


def _name_patterns(names: list[str]) -> list[re.Pattern]:
    """Full names first (longest first), then each part of two or more
    letters. A part directly after "Dr" is left alone so the doctor's own
    surname, often shared with patients, survives."""
    fulls, parts = set(), set()
    for name in names:
        name = " ".join((name or "").split())
        if not name:
            continue
        fulls.add(name)
        for part in re.split(r"[^A-Za-z]+", name):
            if len(part) >= 2:
                parts.add(part)
    patterns = [
        re.compile(r"\b" + re.escape(full) + r"\b", re.IGNORECASE)
        for full in sorted(fulls, key=len, reverse=True)
    ]
    patterns += [
        re.compile(r"(?<!Dr\. )(?<!Dr )(?<!Dr\.)\b" + re.escape(part) + r"\b", re.IGNORECASE)
        for part in sorted(parts, key=len, reverse=True)
    ]
    return patterns


def deidentify(text: str | None, *, names: list[str], ipd_numbers: list[str] = ()) -> str:
    """Remove patient identifiers from free text. Over-redaction is accepted;
    under-redaction is the failure this exists to prevent."""
    if not text:
        return ""
    out = text
    for ipd in ipd_numbers:
        if ipd and ipd.strip():
            out = re.sub(re.escape(ipd.strip()), "[IPD]", out, flags=re.IGNORECASE)
    out = _PHONE.sub("[phone]", out)
    out = _DATE.sub("[date]", out)
    for pattern in _name_patterns(names):
        out = pattern.sub("the child", out)
    return _REPEATED_CHILD.sub("the child", out)


# ---------- Prompt construction ----------

_SCALAR_LABELS = (
    ("age_at_admission", "Age"),
    ("weight", "Weight"),
    ("height", "Height"),
    ("diagnosis", "Diagnosis"),
    ("history", "History"),
    ("examination_findings", "General examination"),
    ("temperature", "Temperature"),
    ("pulse", "Pulse"),
    ("bp", "Blood pressure"),
    ("resp_rate", "Respiratory rate"),
    ("spo2", "SpO2"),
    ("throat_findings", "Throat"),
    ("respiratory_system", "Respiratory system"),
    ("cvs_system", "CVS"),
    ("abdominal_exam", "Abdomen"),
    ("cns_system", "CNS"),
    ("investigations", "Investigations"),
)
_SIGN_LABELS = (
    ("pallor", "pallor"), ("icterus", "icterus"), ("rash", "rash"),
    ("cyanosis", "cyanosis"), ("meningeal_signs", "meningeal signs"),
    ("dehydration_signs", "dehydration"),
)


def _get(obj, key):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def _treatment_line(item) -> str:
    parts = [_get(item, k) for k in ("drug", "dose", "route", "frequency", "duration")]
    line = " ".join(p.strip() for p in parts if p and p.strip())
    instructions = _get(item, "instructions")
    if instructions and instructions.strip():
        line += f" ({instructions.strip()})"
    return line


def _length_of_stay(admission, discharge) -> str | None:
    if not isinstance(admission, datetime) or not isinstance(discharge, datetime):
        return None
    days = (discharge.date() - admission.date()).days
    if days < 0:
        return None
    return "less than a day" if days == 0 else f"{days} day{'s' if days != 1 else ''}"


def query_text(fields) -> str:
    """The summary-section text stored records are embedded by, so the
    similarity is like for like."""
    return embeddings.section_texts(fields).get("summary", "")


def record_text(fields, *, sex: str | None, names: list[str]) -> str:
    """The current record as labelled lines, identifiers removed. Only
    clinical content is included: no name, dates, IPD number, ward or
    doctor."""
    ipd = [_get(fields, "ipd_number") or ""]
    clean = lambda v: deidentify(v, names=names, ipd_numbers=ipd).strip()  # noqa: E731

    lines = []
    if sex:
        lines.append(f"Sex: {sex}")
    stay = _length_of_stay(_get(fields, "admission_date"), _get(fields, "discharge_date"))
    if stay:
        lines.append(f"Length of stay: {stay}")
    for key, label in _SCALAR_LABELS:
        value = clean(_get(fields, key))
        if value:
            lines.append(f"{label}: {value}")

    present = [label for key, label in _SIGN_LABELS if _get(fields, key) == "yes"]
    absent = [label for key, label in _SIGN_LABELS if _get(fields, key) == "no"]
    if present:
        lines.append("Signs present: " + ", ".join(present))
    if absent:
        lines.append("Signs absent: " + ", ".join(absent))

    items = _get(fields, "treatment_items") or []
    for category, label in (("hospital", "Treatment given in hospital"),
                            ("discharge", "Medicines on discharge")):
        rows = [clean(_treatment_line(t)) for t in items if _get(t, "category") == category]
        rows = [r for r in rows if r]
        if rows:
            lines.append(label + ":\n" + "\n".join(f"- {r}" for r in rows))

    notes = clean(_get(fields, "course_in_hospital"))
    if notes:
        lines.append(f"Doctor's notes for this section so far: {notes}")
    return "\n".join(lines)


def has_clinical_content(fields) -> bool:
    return bool(query_text(fields) or (_get(fields, "course_in_hospital") or "").strip())


def select_exemplars(
    db: Session, fields, *, exclude_record_id: int | None, limit: int,
) -> tuple[list[tuple[int, str]], str | None]:
    """The most similar finalised past records that have a course-in-hospital
    section, each de-identified with its own patient's details. Returns
    (exemplars, note); the note explains an empty list when retrieval was
    not possible, so the caller can show it instead of failing silently."""
    text = query_text(fields)
    if not text:
        return [], None
    try:
        vec = embeddings.embed_text(text)
        ranked = embeddings.rank_similar(
            db, vec, limit=limit, exclude_record_id=exclude_record_id,
            where=(
                models.DischargeRecord.status == "final",
                models.DischargeRecord.course_in_hospital.is_not(None),
                func.length(func.trim(models.DischargeRecord.course_in_hospital)) > 0,
            ),
        )
    except (embeddings.EmbeddingUnavailable, embeddings.EmbeddingMismatch) as exc:
        logger.warning("Drafting without similar cases: %s", exc)
        return [], f"Similar past cases could not be searched: {exc}"
    if not ranked:
        return [], "No finalised past cases with a course-in-hospital section yet."

    ids = [record_id for record_id, _ in ranked]
    records = {
        r.id: r for r in db.scalars(
            select(models.DischargeRecord)
            .options(selectinload(models.DischargeRecord.patient))
            .where(models.DischargeRecord.id.in_(ids))
        )
    }
    out = []
    for record_id in ids:
        record = records.get(record_id)
        if record is None:
            continue
        names = [record.patient.name] if record.patient else []
        ipd = [record.ipd_number or ""]
        diagnosis = deidentify(record.diagnosis, names=names, ipd_numbers=ipd).strip()
        course = deidentify(record.course_in_hospital, names=names, ipd_numbers=ipd).strip()
        if len(course) > EXEMPLAR_COURSE_CHARS:
            course = course[:EXEMPLAR_COURSE_CHARS].rsplit(" ", 1)[0] + " …"
        out.append((record_id, f"Diagnosis: {diagnosis or 'not recorded'}\nCourse in hospital: {course}"))
    return out, None


SYSTEM_PROMPT = """\
You draft the "Course in hospital" section of a paediatric discharge summary \
for a small nursing home in India. The treating doctor reviews and edits every \
draft before it is used, so accuracy matters more than completeness.

How to write it:
- Use only facts stated in <current_record>. Do not add investigations, \
results, drugs, doses, durations, complications, procedures or improvements \
that it does not state.
- <similar_cases> are past discharges written by the same doctor. Use them \
only to match the doctor's usual style, length and order of events. Never \
copy a fact from them into the draft.
- If the record lacks something this section normally states (for example the \
response to treatment, how long IV therapy ran, or the child's condition at \
discharge), leave it out of the draft and add a short question about it to \
missing_information instead of guessing.
- If <current_record> contains "Doctor's notes for this section so far", build \
the draft around those notes; they are the doctor's own account.
- Write concise clinical English as used in Indian discharge summaries: past \
tense, third person, "the child", no headings, no bullet points, usually three \
to six sentences.
- Identifiers have been removed and appear as "the child", [IPD], [date] or \
[phone]. Do not try to restore them.
- If the record holds too little to write a meaningful section, return an \
empty course_in_hospital and say what is needed in missing_information."""


def build_user_message(context: DraftContext) -> str:
    if context.exemplars:
        cases = "\n".join(
            f'<case n="{n}">\n{text}\n</case>'
            for n, (_, text) in enumerate(context.exemplars, start=1)
        )
    else:
        cases = "(none available)"
    return (
        f"<current_record>\n{context.record_text}\n</current_record>\n\n"
        f"<similar_cases>\n{cases}\n</similar_cases>\n\n"
        "Draft the course in hospital for the current record."
    )


def build_context(
    db: Session, fields, *, sex: str | None, names: list[str],
    exclude_record_id: int | None,
) -> DraftContext:
    exemplars, note = select_exemplars(
        db, fields, exclude_record_id=exclude_record_id, limit=config.LLM_EXEMPLARS,
    )
    return DraftContext(
        record_text=record_text(fields, sex=sex, names=names),
        exemplars=exemplars,
        exemplar_note=note,
    )


# ---------- The model call ----------

def interpret(stop_reason: str | None, parsed: CourseDraft | None, stop_details=None) -> CourseDraft:
    """Turn the API's stop reason and parsed output into a draft or a clear
    error. Checked before the content is used."""
    if stop_reason == "refusal":
        category = getattr(stop_details, "category", None) if stop_details else None
        raise DraftDeclined(
            "The AI model declined to draft this section"
            + (f" (category: {category})" if category else "")
            + ". Write it by hand."
        )
    if stop_reason == "max_tokens":
        raise DraftingFailed("The draft was cut off before it finished. Try again.")
    if parsed is None:
        raise DraftingFailed("The AI model returned no usable draft. Try again.")
    return parsed


def draft_course(context: DraftContext) -> DraftResult:
    st = status()
    if not st.enabled:
        raise DraftingUnavailable(st.reason)

    user_message = build_user_message(context)
    if len(user_message) > MAX_INPUT_CHARS:
        raise DraftInputTooLong(
            f"This record is too long to draft from ({len(user_message)} characters; "
            f"the limit is {MAX_INPUT_CHARS})."
        )

    import anthropic

    try:
        response = _get_client().beta.messages.parse(
            model=config.LLM_MODEL,
            max_tokens=config.LLM_MAX_TOKENS,
            output_config={"effort": config.LLM_EFFORT},
            output_format=CourseDraft,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            **_fallback_kwargs(config.LLM_MODEL),
        )
    except anthropic.APIStatusError as exc:
        logger.error("Drafting API error %s (request %s)", exc.status_code,
                     getattr(exc, "request_id", None))
        raise DraftingFailed(f"The AI service returned an error ({exc.status_code}).") from exc
    except anthropic.APIConnectionError as exc:  # includes timeouts
        logger.error("Drafting API unreachable: %s", type(exc).__name__)
        raise DraftingFailed("The AI service could not be reached. Try again.") from exc

    draft = interpret(
        response.stop_reason, getattr(response, "parsed_output", None),
        getattr(response, "stop_details", None),
    )
    usage = response.usage
    return DraftResult(
        course_in_hospital=draft.course_in_hospital.strip(),
        missing_information=[q.strip() for q in draft.missing_information if q and q.strip()],
        model=response.model,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        exemplar_ids=[record_id for record_id, _ in context.exemplars],
    )


def warn_if_misconfigured() -> None:
    if config.LLM_ENABLED and not _api_key_present():
        logger.warning("DISCHARGE_LLM_ENABLED=1 but no API key is set; "
                       "AI drafting will refuse requests.")
    elif config.LLM_ENABLED:
        logger.info("AI drafting enabled with %s (effort %s)", config.LLM_MODEL, config.LLM_EFFORT)
