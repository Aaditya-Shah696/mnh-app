"""AI drafting endpoints. Off unless DISCHARGE_LLM_ENABLED=1; every request
that reaches the model is audited, whatever the outcome."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import auth, config, models, schemas
from ..audit import audit
from ..database import get_db
from ..services import drafting
from .patients import get_patient_or_404
from .records import get_record_or_404

router = APIRouter(
    prefix="/api/draft", tags=["draft"], dependencies=[Depends(auth.current_user)]
)

draft_limiter = auth.SlidingWindowLimiter(config.LLM_USER_HOURLY_LIMIT, 3600)


@router.get("/status", response_model=schemas.DraftStatus)
def draft_status():
    st = drafting.status()
    return schemas.DraftStatus(enabled=st.enabled, model=st.model, reason=st.reason)


@router.post("/course-in-hospital", response_model=schemas.CourseDraftOut)
def draft_course_in_hospital(
    payload: schemas.DraftRequest, request: Request,
    user: models.User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    """Draft the course-in-hospital section from the in-progress form.
    Returns a draft for the doctor to review; nothing is saved."""
    st = drafting.status()
    if not st.enabled:
        raise HTTPException(status_code=503, detail=st.reason)

    patient = None
    if payload.record_id is not None:
        record = get_record_or_404(payload.record_id, db)
        if payload.patient_id is not None and payload.patient_id != record.patient_id:
            raise HTTPException(status_code=422, detail="record_id belongs to a different patient")
        patient = record.patient
    elif payload.patient_id is not None:
        patient = get_patient_or_404(payload.patient_id, db)

    if not drafting.has_clinical_content(payload):
        raise HTTPException(
            status_code=422,
            detail="Fill in the diagnosis, history or treatment first; there is nothing to draft from.",
        )
    if not draft_limiter.check(str(user.id)):
        raise HTTPException(
            status_code=429,
            detail=f"Drafting limit reached ({config.LLM_USER_HOURLY_LIMIT} per hour). Try again later.",
            headers={"Retry-After": "600"},
        )

    names = [n for n in (patient.name if patient else None, payload.patient_name) if n]
    sex = (patient.sex if patient else None) or payload.patient_sex
    context = drafting.build_context(
        db, payload, sex=sex, names=names, exclude_record_id=payload.record_id,
    )
    exemplar_ids = [record_id for record_id, _ in context.exemplars]

    def _audit(outcome: str, **extra) -> None:
        audit(db, "record.draft", request=request, user=user, entity_type="record",
              entity_id=payload.record_id,
              detail={"section": "course_in_hospital", "outcome": outcome,
                      "patient_id": patient.id if patient else None,
                      "exemplars": exemplar_ids, **extra})
        db.commit()

    try:
        result = drafting.draft_course(context)
    except drafting.DraftingUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except drafting.DraftInputTooLong as exc:  # nothing was sent
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except drafting.DraftDeclined as exc:
        _audit("declined", model=config.LLM_MODEL)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except drafting.DraftingFailed as exc:
        _audit("failed", model=config.LLM_MODEL)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    _audit("drafted", model=result.model, input_tokens=result.input_tokens,
           output_tokens=result.output_tokens,
           missing_items=len(result.missing_information))
    return schemas.CourseDraftOut(
        course_in_hospital=result.course_in_hospital,
        missing_information=result.missing_information,
        exemplar_record_ids=result.exemplar_ids,
        exemplar_note=context.exemplar_note,
        model=result.model,
    )
