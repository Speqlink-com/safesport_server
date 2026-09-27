import uuid
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import current_user, verify_csrf
from app.db.session import get_db
from app.models.auth import User
from app.models.institution import Institution, Sport
from app.models.ppe import PPEAssessment, PPEConsent
from app.schemas.ppe import (
    CertificateVerifyResponse,
    PPEAssessmentPayload,
    PPEAthleteResponse,
    PPEConsentPayload,
    PPEConsentResponse,
    PPEEncounterResponse,
    PPEPhysioReviewRequest,
    PPEStartRequest,
    PPEWorkspaceResponse,
    PPENoticeResponse,
)
from app.services.certificate_service import build_certificate_pdf, certificate_context

router = APIRouter(prefix="/ppe", tags=["ppe"] )
CLINICAL_ROLES = {"clinician", "physiotherapist", "operations", "sys-admin"}
INSTITUTION_ROLES = {"institution", "coach"}


def _today() -> str:
    return date.today().isoformat()


def _athlete_query(user: User):
    return select(User).where(User.role == "athlete", User.is_active.is_(True))


def _visible_athletes(db: Session, user: User) -> list[User]:
    if user.role == "athlete":
        return [user]
    if user.role == "guardian":
        athlete_id = str((user.profile_data or {}).get("athlete_id") or "")
        if athlete_id:
            try:
                athlete = db.get(User, uuid.UUID(athlete_id))
                return [athlete] if athlete and athlete.role == "athlete" else []
            except ValueError:
                return []
        return []
    if user.role in CLINICAL_ROLES | INSTITUTION_ROLES:
        return list(db.scalars(_athlete_query(user).order_by(User.created_at.desc())).all())
    return []


def _require_athlete_access(db: Session, user: User, athlete_id: str) -> User:
    try:
        athlete_uuid = uuid.UUID(athlete_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Athlete not found") from exc
    athlete = db.get(User, athlete_uuid)
    if not athlete or athlete.role != "athlete":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Athlete not found")
    if user.role == "athlete" and user.id != athlete.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only access your own PPE record")
    if user.role == "guardian" and str((user.profile_data or {}).get("athlete_id") or "") != str(athlete.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This athlete is not linked to your account")
    if user.role not in {"athlete", "guardian"} | CLINICAL_ROLES | INSTITUTION_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "PPE access is not available for this role")
    return athlete


def _active_assessment(db: Session, athlete: User) -> PPEAssessment | None:
    return db.scalar(
        select(PPEAssessment)
        .where(PPEAssessment.athlete_user_id == athlete.id, PPEAssessment.finalized.is_(False))
        .order_by(PPEAssessment.created_at.desc())
    )


def _ensure_assessment(db: Session, athlete: User) -> PPEAssessment:
    assessment = _active_assessment(db, athlete)
    if assessment:
        return assessment
    assessment = PPEAssessment(athlete_user_id=athlete.id, status="draft")
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


def _public_org_sport(db: Session, profile: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    org = None
    sport = None
    team = None
    if profile.get("organization_id"):
        try:
            inst = db.get(Institution, uuid.UUID(str(profile["organization_id"])))
        except ValueError:
            inst = None
        if inst:
            org = {"id": str(inst.id), "name": inst.name, "type": inst.type, "logo": inst.logo_path}
    if not org and profile.get("organization_name"):
        org = {"id": str(profile.get("organization_id") or ""), "name": profile["organization_name"], "type": "school"}
    if profile.get("sport_id"):
        try:
            sport_model = db.get(Sport, uuid.UUID(str(profile["sport_id"])))
        except ValueError:
            sport_model = None
        if sport_model:
            sport = {"id": str(sport_model.id), "name": sport_model.name, "category": "other"}
    if not sport and profile.get("sport_name"):
        sport = {"id": str(profile.get("sport_id") or ""), "name": profile["sport_name"], "category": "other"}
    if org and sport:
        team = {"id": f"team-{sport['id']}", "name": sport["name"], "ageGroup": "Open", "sport": sport, "organizationId": org["id"]}
    return org, sport, team


def _age(dob: str) -> int:
    try:
        born = date.fromisoformat(dob)
    except ValueError:
        return 0
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _readiness(decision: str) -> str:
    if decision == "cleared":
        return "ready"
    if decision in {"cleared_with_monitoring", "sport_specific_restriction"}:
        return "ready_with_restrictions"
    if decision == "pending_evaluation":
        return "under_review"
    return "not_ready"


def _athlete_response(db: Session, athlete: User, assessments: list[PPEAssessment]) -> PPEAthleteResponse:
    profile = dict(athlete.profile_data or {})
    org, sport, team = _public_org_sport(db, profile)
    latest_final = next((item for item in assessments if item.finalized), None)
    decision = latest_final.decision if latest_final else "pending_evaluation"
    review_date = latest_final.review_date.isoformat() if latest_final and latest_final.review_date else None
    dob = profile.get("date_of_birth") or "2000-01-01"
    return PPEAthleteResponse(
        id=str(athlete.id),
        firstName=athlete.first_name,
        lastName=athlete.last_name,
        dateOfBirth=dob,
        age=_age(dob),
        gender=str(profile.get("gender") or "other"),
        currentOrganization=org,
        currentTeam=team,
        currentSport=sport,
        eligibilityStatus=decision,
        readiness=_readiness(decision),
        nextReview=review_date,
        organizations=[{"organizationId": org["id"], "organization": org, "joinedAt": athlete.created_at.date().isoformat(), "status": "active"}] if org else [],
        teams=[{"teamId": team["id"], "team": team, "sport": sport, "joinedAt": athlete.created_at.date().isoformat(), "status": "active"}] if team and sport else [],
        createdAt=athlete.created_at.isoformat(),
        updatedAt=athlete.updated_at.isoformat(),
    )


def _consent_response(athlete_id: str, consent: PPEConsent | None) -> PPEConsentResponse:
    if not consent:
        return PPEConsentResponse(athlete_id=athlete_id, clinical="deferred", video=False, research=False, assent=False, signer="", version="PPE privacy v1.0", at="")
    return PPEConsentResponse(
        athlete_id=athlete_id,
        clinical=consent.clinical,
        video=consent.video,
        research=consent.research,
        assent=consent.assent,
        signer=consent.signer,
        version=consent.version,
        at=(consent.consented_at or consent.updated_at).isoformat(),
    )


def _payload(assessment: PPEAssessment) -> dict[str, Any]:
    data: dict[str, Any] = {}
    data.update(assessment.history_payload or {})
    data.update(assessment.clinical_payload or {})
    return data


def _encounter_response(assessment: PPEAssessment) -> PPEEncounterResponse:
    data = _payload(assessment)
    review_date = assessment.review_date.isoformat() if assessment.review_date else str(data.get("reviewDate") or "")
    data.update(
        {
            "id": str(assessment.id),
            "athleteId": str(assessment.athlete_user_id),
            "date": assessment.created_at.date().isoformat(),
            "status": assessment.status,
            "reviewed": assessment.reviewed,
            "historySubmitted": assessment.history_submitted,
            "finalized": assessment.finalized,
            "decision": assessment.decision,
            "restrictions": assessment.restrictions,
            "plan": assessment.plan,
            "reviewDate": review_date,
            "rationale": assessment.rationale,
            "signature": assessment.signature,
            "certificateCode": assessment.certificate_code,
            "certificateIssuedAt": assessment.certificate_issued_at,
            "physioStatus": assessment.physio_status,
            "physioNote": assessment.physio_note,
        }
    )
    return PPEEncounterResponse(**data)


def _claim_or_require_clinician(assessment: PPEAssessment, user: User) -> None:
    if user.role != "clinician":
        return
    if assessment.clinician_user_id and assessment.clinician_user_id != user.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This PPE assessment is already assigned to another clinician",
        )
    assessment.clinician_user_id = user.id


def _assessment_from_payload(assessment: PPEAssessment, payload: PPEAssessmentPayload) -> None:
    data = payload.model_dump()
    assessment.history_payload = {
        "history": data["history"],
        "followups": data["followups"],
        "historyAnswers": data["historyAnswers"],
        "historyDetails": data["historyDetails"],
        "historyResolutions": data["historyResolutions"],
        "historySubmitted": data["historySubmitted"],
        "injuries": data["injuries"],
        "concussion": data["concussion"],
    }
    assessment.clinical_payload = {
        "exam": data["exam"],
        "examNotes": data["examNotes"],
        "baseline": data["baseline"],
        "baselineNotes": data["baselineNotes"],
        "vitals": data["vitals"],
        "sportNotes": data["sportNotes"],
        "careReview": data["careReview"],
        "reassessmentRequestIds": data["reassessmentRequestIds"],
    }
    assessment.reviewed = data["reviewed"]
    assessment.history_submitted = data["historySubmitted"]
    assessment.status = data["status"]
    assessment.decision = data["decision"]
    assessment.restrictions = data["restrictions"]
    assessment.plan = data["plan"]
    assessment.rationale = data["rationale"]
    assessment.signature = data["signature"]
    assessment.finalized = data["finalized"]
    assessment.review_date = date.fromisoformat(data["reviewDate"]) if data["reviewDate"] else None


def _notices(user: User, athletes: list[User], consents: dict[str, PPEConsentResponse], encounters: list[PPEEncounterResponse]) -> list[PPENoticeResponse]:
    output: list[PPENoticeResponse] = []
    now = datetime.now(timezone.utc).isoformat()
    for athlete in athletes:
        aid = str(athlete.id)
        active = next((e for e in encounters if e.athleteId == aid and not e.finalized), None)
        latest = next((e for e in encounters if e.athleteId == aid), None)
        name = f"{athlete.first_name} {athlete.last_name}"
        if user.role == "athlete" and active and not active.historySubmitted:
            output.append(PPENoticeResponse(id=f"ppe-start-{aid}", role=user.role, title="Start your PPE health questionnaire", path="questionnaires", date=now))
        if user.role == "clinician" and active and active.historySubmitted and not active.reviewed:
            output.append(PPENoticeResponse(id=f"ppe-review-{active.id}", role="clinician", title=f"PPE questionnaire ready for {name}", path=f"assessments/{active.id}", date=now))
        if user.role == "physiotherapist" and latest and latest.physioStatus == "pending":
            output.append(PPENoticeResponse(id=f"ppe-physio-{latest.id}", role="physiotherapist", title=f"Functional review requested for {name}", path="rehabilitation", date=now))
        if user.role in {"athlete", "guardian"} and latest and latest.finalized:
            output.append(PPENoticeResponse(id=f"ppe-cert-{latest.id}", role=user.role, title="Your participation certificate is available", path="certificates", date=now))
    return output


@router.get("/workspace", response_model=PPEWorkspaceResponse)
def workspace(user: User = Depends(current_user), db: Session = Depends(get_db)) -> PPEWorkspaceResponse:
    athletes = _visible_athletes(db, user)
    if user.role == "athlete" and athletes:
        _ensure_assessment(db, athletes[0])
    athlete_ids = [athlete.id for athlete in athletes]
    assessments = list(db.scalars(select(PPEAssessment).where(PPEAssessment.athlete_user_id.in_(athlete_ids)).order_by(PPEAssessment.created_at.desc())).all()) if athlete_ids else []
    by_athlete: dict[uuid.UUID, list[PPEAssessment]] = {athlete.id: [] for athlete in athletes}
    for item in assessments:
        by_athlete.setdefault(item.athlete_user_id, []).append(item)
    consents = list(db.scalars(select(PPEConsent).where(PPEConsent.athlete_user_id.in_(athlete_ids))).all()) if athlete_ids else []
    consent_map = {str(item.athlete_user_id): item for item in consents}
    athlete_responses = [_athlete_response(db, athlete, by_athlete.get(athlete.id, [])) for athlete in athletes]
    consent_responses = {str(athlete.id): _consent_response(str(athlete.id), consent_map.get(str(athlete.id))) for athlete in athletes}
    encounter_responses = [_encounter_response(item) for item in assessments]
    return PPEWorkspaceResponse(
        athletes=athlete_responses,
        consents=consent_responses,
        encounters=encounter_responses,
        notices=_notices(user, athletes, consent_responses, encounter_responses),
    )


@router.put("/consents/{athlete_id}", response_model=PPEConsentResponse, dependencies=[Depends(verify_csrf)])
def save_consent(athlete_id: str, payload: PPEConsentPayload, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PPEConsentResponse:
    athlete = _require_athlete_access(db, user, athlete_id)
    consent = db.scalar(select(PPEConsent).where(PPEConsent.athlete_user_id == athlete.id))
    if not consent:
        consent = PPEConsent(athlete_user_id=athlete.id)
        db.add(consent)
    consent.clinical = payload.clinical
    consent.video = payload.video
    consent.research = payload.research
    consent.assent = payload.assent
    consent.signer = payload.signer.strip()
    consent.version = payload.version
    consent.consented_at = datetime.now(timezone.utc)
    active = _active_assessment(db, athlete)
    if active and not active.finalized:
        active.status = "in_progress" if consent.clinical == "obtained" else "blocked"
    db.commit()
    db.refresh(consent)
    return _consent_response(str(athlete.id), consent)


@router.post("/questionnaires/{athlete_id}/draft", response_model=PPEEncounterResponse, dependencies=[Depends(verify_csrf)])
def save_questionnaire_draft(athlete_id: str, payload: PPEAssessmentPayload, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PPEEncounterResponse:
    athlete = _require_athlete_access(db, user, athlete_id)
    assessment = _ensure_assessment(db, athlete)
    payload.status = "draft"
    payload.historySubmitted = False
    payload.reviewed = False
    _assessment_from_payload(assessment, payload)
    db.commit()
    db.refresh(assessment)
    return _encounter_response(assessment)


@router.post("/questionnaires/{athlete_id}/submit", response_model=PPEEncounterResponse, dependencies=[Depends(verify_csrf)])
def submit_questionnaire(athlete_id: str, payload: PPEAssessmentPayload, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PPEEncounterResponse:
    athlete = _require_athlete_access(db, user, athlete_id)
    consent = db.scalar(select(PPEConsent).where(PPEConsent.athlete_user_id == athlete.id))
    if not consent or consent.clinical != "obtained":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Clinical consent is required before questionnaire submission")
    assessment = _ensure_assessment(db, athlete)
    payload.status = "needs_review"
    payload.historySubmitted = True
    payload.reviewed = False
    _assessment_from_payload(assessment, payload)
    db.commit()
    db.refresh(assessment)
    return _encounter_response(assessment)


@router.post("/assessments/start", response_model=PPEEncounterResponse, dependencies=[Depends(verify_csrf)])
def start_assessment(payload: PPEStartRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PPEEncounterResponse:
    if user.role not in CLINICAL_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Clinical role is required")
    athlete = _require_athlete_access(db, user, payload.athlete_id)
    assessment = _ensure_assessment(db, athlete)
    _claim_or_require_clinician(assessment, user)
    if assessment.status == "draft":
        assessment.status = "in_progress"
    db.commit()
    db.refresh(assessment)
    return _encounter_response(assessment)


@router.put("/assessments/{assessment_id}", response_model=PPEEncounterResponse, dependencies=[Depends(verify_csrf)])
def save_assessment(assessment_id: uuid.UUID, payload: PPEAssessmentPayload, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PPEEncounterResponse:
    if user.role not in CLINICAL_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Clinical role is required")
    assessment = db.get(PPEAssessment, assessment_id)
    if not assessment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assessment not found")
    _require_athlete_access(db, user, str(assessment.athlete_user_id))
    _claim_or_require_clinician(assessment, user)
    payload.finalized = False
    payload.status = "in_progress"
    _assessment_from_payload(assessment, payload)
    db.commit()
    db.refresh(assessment)
    return _encounter_response(assessment)


@router.post("/assessments/{assessment_id}/finalize", response_model=PPEEncounterResponse, dependencies=[Depends(verify_csrf)])
def finalize_assessment(assessment_id: uuid.UUID, payload: PPEAssessmentPayload, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PPEEncounterResponse:
    if user.role != "clinician":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Clinician role is required")
    assessment = db.get(PPEAssessment, assessment_id)
    if not assessment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assessment not found")
    _require_athlete_access(db, user, str(assessment.athlete_user_id))
    _claim_or_require_clinician(assessment, user)
    payload.finalized = True
    payload.status = "complete"
    _assessment_from_payload(assessment, payload)
    if not assessment.signature.strip():
        assessment.signature = f"{user.first_name} {user.last_name}"
    assessment.finalized = True
    assessment.status = "complete"
    assessment.certificate_code = assessment.certificate_code or f"SAFE-{str(assessment.id)[:8].upper()}"
    assessment.certificate_issued_at = datetime.now(timezone.utc)
    assessment.physio_status = "pending" if assessment.decision != "cleared" else "not_required"
    db.commit()
    db.refresh(assessment)
    return _encounter_response(assessment)


@router.post("/assessments/{assessment_id}/physio-review", response_model=PPEEncounterResponse, dependencies=[Depends(verify_csrf)])
def physio_review(assessment_id: uuid.UUID, payload: PPEPhysioReviewRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PPEEncounterResponse:
    if user.role not in {"physiotherapist", "clinician"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Physiotherapist or clinician role is required")
    assessment = db.get(PPEAssessment, assessment_id)
    if not assessment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assessment not found")
    assessment.physio_user_id = user.id if user.role == "physiotherapist" else assessment.physio_user_id
    assessment.physio_status = payload.status
    assessment.physio_note = payload.note.strip()
    db.commit()
    db.refresh(assessment)
    return _encounter_response(assessment)


@router.get("/certificates/{assessment_id}")
def certificate(assessment_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    assessment = db.get(PPEAssessment, assessment_id)
    if not assessment or not assessment.finalized:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Certificate is not available")
    athlete = _require_athlete_access(db, user, str(assessment.athlete_user_id))
    context = certificate_context(athlete, assessment)
    if not context.institution_logo_url:
        profile = dict(athlete.profile_data or {})
        try:
            institution = db.get(Institution, uuid.UUID(str(profile.get("organization_id") or "")))
        except ValueError:
            institution = None
        if institution and institution.logo_path:
            context = replace(context, institution_logo_url=institution.logo_path)
    pdf = build_certificate_pdf(context)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=safesport-certificate-{context.verification_code}.pdf",
            "X-Certificate-Code": context.verification_code,
        },
    )


@router.get("/certificates/verify/{code}", response_model=CertificateVerifyResponse)
def verify_certificate(code: str, db: Session = Depends(get_db)) -> CertificateVerifyResponse:
    assessment = db.scalar(select(PPEAssessment).where(PPEAssessment.certificate_code == code.upper()))
    if not assessment or not assessment.finalized:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Certificate not found")
    athlete = db.get(User, assessment.athlete_user_id)
    if not athlete:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Certificate not found")
    context = certificate_context(athlete, assessment)
    return CertificateVerifyResponse(
        valid=True,
        code=context.verification_code,
        athlete_name=context.athlete_name,
        athlete_id=context.athlete_id,
        institution=context.institution,
        sport=context.sport,
        eligibility=context.decision,
        restrictions=context.restrictions,
        review_date=context.review_date,
        clinician_signature=context.clinician_signature,
        issued_at=assessment.certificate_issued_at,
    )
