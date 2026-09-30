import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import current_user, verify_csrf
from app.db.session import SessionLocal, get_db
from app.models.auth import User
from app.models.care import CareRecord
from app.models.institution import Institution
from app.models.messaging import Conversation, ConversationMember, Message
from app.models.movement import MovementScreening, MovementSession
from app.schemas.movement import (
    MovementReportPayload,
    MovementReviewPayload,
    MovementScreeningCreate,
    MovementScreeningResponse,
    MovementSessionCreate,
    MovementSessionResponse,
    MovementVideoUploadResponse,
    MovementWorkspaceResponse,
)
from app.services.cloudinary_service import upload_movement_video
from app.services.movement_report_service import build_movement_report_pdf
from app.services.movement_ai_service import run_movement_analysis

router = APIRouter(prefix="/movement", tags=["movement screening"])
CLINICAL_ROLES = {"clinician", "physiotherapist", "operations", "sys-admin"}
SCHEDULER_ROLES = {"coach", "institution", "operations", "sys-admin"}


def _name(user: User) -> str:
    return f"{user.first_name} {user.last_name}".strip()


def _institution_id(user: User, db: Session) -> uuid.UUID | None:
    raw = (user.profile_data or {}).get("institution_id") or (user.profile_data or {}).get("organization_id")
    if raw:
        try:
            return uuid.UUID(str(raw))
        except ValueError:
            return None
    if user.role == "institution":
        institution = db.scalar(select(Institution).where(Institution.contact_email == user.email))
        return institution.id if institution else None
    return None


def _athlete_in_institution(athlete: User, institution_id: uuid.UUID | None) -> bool:
    if not institution_id:
        return False
    return str((athlete.profile_data or {}).get("organization_id") or (athlete.profile_data or {}).get("institution_id") or "") == str(institution_id)


def _visible_athletes(user: User, db: Session) -> list[User]:
    if user.role == "athlete":
        return [user]
    if user.role == "guardian":
        try:
            athlete = db.get(User, uuid.UUID(str((user.profile_data or {}).get("athlete_id") or "")))
        except ValueError:
            return []
        return [athlete] if athlete and athlete.role == "athlete" else []
    athletes = list(db.scalars(select(User).where(User.role == "athlete", User.is_active.is_(True)).order_by(User.created_at.desc())).all())
    if user.role in {"coach", "institution"}:
        inst = _institution_id(user, db)
        return [athlete for athlete in athletes if _athlete_in_institution(athlete, inst)]
    if user.role in CLINICAL_ROLES:
        return athletes
    return []


def _require_athlete_by_safe_id(safesport_id: str, user: User, db: Session) -> User:
    raw = safesport_id.strip()
    athlete = db.scalar(select(User).where(User.safesport_id == raw.upper(), User.role == "athlete", User.is_active.is_(True)))
    if not athlete:
        try:
            athlete = db.get(User, uuid.UUID(raw))
        except ValueError:
            athlete = None
    if not athlete or athlete.role != "athlete" or athlete.id not in {item.id for item in _visible_athletes(user, db)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Athlete is not available in your scope")
    return athlete


def _session_response(session: MovementSession) -> MovementSessionResponse:
    return MovementSessionResponse(
        id=str(session.id), institution_id=str(session.institution_id) if session.institution_id else None,
        institution_name=session.institution.name if session.institution else "", title=session.title,
        scheduled_at=session.scheduled_at, location=session.location, drill=session.drill, camera_view=session.camera_view,
        instructions_html=session.instructions_html, status=session.status, created_at=session.created_at,
    )


def _screening_response(screening: MovementScreening) -> MovementScreeningResponse:
    return MovementScreeningResponse(
        id=str(screening.id), session_id=str(screening.session_id) if screening.session_id else None,
        athlete_id=str(screening.athlete_user_id), athlete_safesport_id=screening.athlete_safesport_id,
        athlete_name=screening.athlete_name, institution_id=str(screening.institution_id) if screening.institution_id else None,
        institution_name=screening.institution.name if screening.institution else "", sport=screening.sport, team=screening.team,
        drill=screening.drill, camera_view=screening.camera_view, status=screening.status, video_url=screening.video_url,
        video_public_id=screening.video_public_id, video_metadata=screening.video_metadata or {}, ai_result=screening.ai_result or {},
        clinician_review=screening.clinician_review or {}, physio_review=screening.physio_review or {},
        report_summary=screening.report_summary, report_generated_at=screening.report_generated_at, created_at=screening.created_at,
    )


async def _run_analysis_background(screening_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        screening = db.get(MovementScreening, screening_id)
        if not screening or not screening.video_url:
            return
        try:
            result = await run_movement_analysis(screening)
        except Exception as exc:
            screening.status = "FAILED"
            screening.ai_result = {
                "status": "FAILED",
                "summary": "AI analysis failed. Please review the video and try again.",
                "error": str(exc)[:500],
            }
        else:
            screening.ai_result = result
            screening.status = "RETAKE_REQUIRED" if result.get("status") == "RETAKE_REQUIRED" else "AWAITING_CLINICIAN_REVIEW"
        db.commit()
    finally:
        db.close()


def _sanitize_html(value: str) -> str:
    value = re.sub(r"<\s*(script|style).*?>.*?<\s*/\s*\1\s*>", "", value or "", flags=re.I | re.S)
    return value[:5000]


def _ai_result(screening: MovementScreening) -> dict[str, object]:
    seed = sum(ord(ch) for ch in str(screening.id))
    risk = ["LOW", "MODERATE", "ELEVATED"][seed % 3]
    score = {"LOW": 28, "MODERATE": 54, "ELEVATED": 72}[risk]
    findings = {
        "LOW": ["Movement control was acceptable for the captured drill.", "Left-right symmetry appeared within expected operational range."],
        "MODERATE": ["Landing or squat control shows a movement pattern that should be coached.", "Recommend prevention-focused neuromuscular control work."],
        "ELEVATED": ["Video suggests reduced lower-limb control during the drill.", "Human review should decide whether physiotherapy input is needed."],
    }[risk]
    return {
        "model": "SafeSport Movement Prototype v1",
        "risk_signal": risk,
        "risk_score": score,
        "confidence": 0.82,
        "quality": {"status": "ACCEPTED", "notes": "Prototype quality gate accepted the uploaded video metadata."},
        "metrics": {"knee_control_index": round(score / 100, 2), "trunk_control_index": round((score - 7) / 100, 2), "symmetry_index": 0.91},
        "summary": f"{screening.drill.replace('_', ' ').title()} produced a {risk.lower()} movement risk signal for clinician decision support.",
        "findings": findings,
        "limitations": ["Prototype analysis package. AI risk signal is not a diagnosis.", "Clinician/physiotherapist interpretation remains authoritative."],
    }


def _ensure_family_group(db: Session, institution_id: uuid.UUID | None, user: User) -> Conversation | None:
    if not institution_id:
        return None
    institution = db.get(Institution, institution_id)
    conv = db.scalar(select(Conversation).where(Conversation.kind == "institution_group", Conversation.institution_id == institution_id))
    if not conv:
        conv = Conversation(kind="institution_group", title=f"{institution.name if institution else 'Institution'} family group", institution_id=institution_id, created_by_user_id=user.id)
        db.add(conv); db.flush()
    users = list(db.scalars(select(User).where(User.is_active.is_(True))).all())
    for person in users:
        profile = person.profile_data or {}
        same_inst = str(profile.get("organization_id") or profile.get("institution_id") or "") == str(institution_id)
        top_role = person.role in {"clinician", "physiotherapist", "sys-admin", "operations"}
        if same_inst or top_role or person.id == user.id:
            exists = db.scalar(select(ConversationMember.id).where(ConversationMember.conversation_id == conv.id, ConversationMember.user_id == person.id))
            if not exists:
                db.add(ConversationMember(conversation_id=conv.id, user_id=person.id))
    return conv


def _broadcast_session(db: Session, session: MovementSession, user: User) -> None:
    conv = _ensure_family_group(db, session.institution_id, user)
    if not conv:
        return
    body = f"AI screening session scheduled: {session.title}\nWhen: {session.scheduled_at or 'To be confirmed'}\nLocation: {session.location or 'To be confirmed'}\nDrill: {session.drill.replace('_', ' ').title()}\n\nPlease open the schedule and prepare athletes for standardized video capture."
    db.add(Message(conversation_id=conv.id, sender_user_id=user.id, body=body, attachment_url="", attachment_name="", attachment_type=""))


def _notices(user: User, sessions: list[MovementSession], screenings: list[MovementScreening]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for session in sessions[:8]:
        output.append({"id": f"move-session-{session.id}", "role": user.role, "title": f"AI screening scheduled: {session.title}", "path": "schedule", "read": False, "date": session.created_at.isoformat()})
    if user.role in {"clinician", "physiotherapist"}:
        for screening in screenings:
            if screening.status in {"AWAITING_CLINICIAN_REVIEW", "REFERRED_TO_PHYSIO"}:
                output.append({"id": f"move-review-{screening.id}", "role": user.role, "title": f"Movement screening review: {screening.athlete_name}", "path": "screenings", "read": False, "date": screening.updated_at.isoformat()})
    return output[:20]


@router.get("/workspace", response_model=MovementWorkspaceResponse)
def workspace(user: User = Depends(current_user), db: Session = Depends(get_db)) -> MovementWorkspaceResponse:
    athletes = _visible_athletes(user, db)
    athlete_ids = [athlete.id for athlete in athletes]
    inst_id = _institution_id(user, db)
    sessions_stmt = select(MovementSession).order_by(MovementSession.created_at.desc())
    if user.role in {"coach", "institution", "athlete", "guardian"} and inst_id:
        sessions_stmt = sessions_stmt.where(MovementSession.institution_id == inst_id)
    sessions = list(db.scalars(sessions_stmt.limit(50)).all())
    screenings_stmt = select(MovementScreening).order_by(MovementScreening.created_at.desc())
    if user.role in {"athlete", "guardian", "coach", "institution"}:
        screenings_stmt = screenings_stmt.where(MovementScreening.athlete_user_id.in_(athlete_ids or [uuid.uuid4()]))
    screenings = list(db.scalars(screenings_stmt.limit(100)).all())
    return MovementWorkspaceResponse(sessions=[_session_response(item) for item in sessions], screenings=[_screening_response(item) for item in screenings], notices=_notices(user, sessions, screenings))


@router.post("/sessions", response_model=MovementSessionResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_csrf)])
def create_session(payload: MovementSessionCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> MovementSessionResponse:
    if user.role not in SCHEDULER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "AI screening sessions require coach, institution or operations access")
    inst_id = _institution_id(user, db)
    session = MovementSession(institution_id=inst_id, title=payload.title.strip(), scheduled_at=payload.scheduled_at, location=payload.location.strip(), drill=payload.drill, camera_view=payload.camera_view, instructions_html=_sanitize_html(payload.instructions_html), created_by_user_id=user.id)
    db.add(session); db.flush()
    db.add(CareRecord(collection="events", athlete_user_id=None, title=session.title, status="scheduled", date=session.scheduled_at, notes=session.instructions_html, assigned="Movement screening team", kind="screening", created_by_user_id=user.id, extra={"movement_session_id": str(session.id)}))
    _broadcast_session(db, session, user)
    db.commit(); db.refresh(session)
    return _session_response(session)


@router.post("/screenings", response_model=MovementScreeningResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_csrf)])
def create_screening(payload: MovementScreeningCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> MovementScreeningResponse:
    if user.role not in CLINICAL_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Clinical staff create AI screening records")
    athlete = _require_athlete_by_safe_id(payload.athlete_safesport_id, user, db)
    profile = athlete.profile_data or {}
    screening = MovementScreening(session_id=uuid.UUID(payload.session_id) if payload.session_id else None, athlete_user_id=athlete.id, institution_id=uuid.UUID(str(profile.get("organization_id"))) if profile.get("organization_id") else None, athlete_safesport_id=athlete.safesport_id, athlete_name=_name(athlete), sport=str(profile.get("sport_name") or ""), team=str(profile.get("team_name") or ""), drill=payload.drill, camera_view=payload.camera_view, created_by_user_id=user.id)
    db.add(screening); db.commit(); db.refresh(screening)
    return _screening_response(screening)


@router.post("/screenings/{screening_id}/video", response_model=MovementVideoUploadResponse, dependencies=[Depends(verify_csrf)])
async def upload_video(screening_id: uuid.UUID, video: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)) -> MovementVideoUploadResponse:
    if user.role not in CLINICAL_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Clinical staff upload screening videos")
    screening = db.get(MovementScreening, screening_id)
    if not screening:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Screening not found")
    upload = await upload_movement_video(video, str(screening.id))
    screening.video_url = str(upload["video_url"]); screening.video_public_id = str(upload["video_public_id"]); screening.video_metadata = upload["metadata"]  # type: ignore[assignment]
    screening.status = "VIDEO_UPLOADED"
    db.commit(); db.refresh(screening)
    return MovementVideoUploadResponse(**upload)


@router.post("/screenings/{screening_id}/analyze", response_model=MovementScreeningResponse, dependencies=[Depends(verify_csrf)])
async def analyze(
    screening_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> MovementScreeningResponse:
    if user.role not in CLINICAL_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Clinical staff start AI analysis")
    screening = db.get(MovementScreening, screening_id)
    if not screening or not screening.video_url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Uploaded screening video not found")
    screening.status = "PROCESSING_POSE"
    db.commit(); db.refresh(screening)
    background_tasks.add_task(_run_analysis_background, screening.id)
    return _screening_response(screening)


@router.post("/screenings/{screening_id}/clinician-review", response_model=MovementScreeningResponse, dependencies=[Depends(verify_csrf)])
def clinician_review(screening_id: uuid.UUID, payload: MovementReviewPayload, user: User = Depends(current_user), db: Session = Depends(get_db)) -> MovementScreeningResponse:
    if user.role not in {"clinician", "sys-admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Clinician role is required")
    screening = db.get(MovementScreening, screening_id)
    if not screening:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Screening not found")
    if payload.decision in {"MODIFY", "REJECT"} and not payload.override_reason.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Override reason is required")
    screening.clinician_review = {"reviewer_id": str(user.id), "reviewer_name": _name(user), "decision": payload.decision, "interpretation": payload.interpretation, "action": payload.action, "override_reason": payload.override_reason, "reviewed_at": datetime.now(timezone.utc).isoformat()}
    screening.status = "REFERRED_TO_PHYSIO" if payload.decision == "REFER_PHYSIO" else "CLINICIAN_REVIEWED"
    db.commit(); db.refresh(screening)
    return _screening_response(screening)


@router.post("/screenings/{screening_id}/physio-review", response_model=MovementScreeningResponse, dependencies=[Depends(verify_csrf)])
def physio_review(screening_id: uuid.UUID, payload: MovementReviewPayload, user: User = Depends(current_user), db: Session = Depends(get_db)) -> MovementScreeningResponse:
    if user.role not in {"physiotherapist", "clinician", "sys-admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Physiotherapist or clinician role is required")
    screening = db.get(MovementScreening, screening_id)
    if not screening:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Screening not found")
    screening.physio_review = {"reviewer_id": str(user.id), "reviewer_name": _name(user), "decision": payload.decision, "interpretation": payload.interpretation, "action": payload.action, "reviewed_at": datetime.now(timezone.utc).isoformat()}
    screening.status = "PHYSIO_REVIEWED"
    db.commit(); db.refresh(screening)
    return _screening_response(screening)


@router.post("/screenings/{screening_id}/report", response_model=MovementScreeningResponse, dependencies=[Depends(verify_csrf)])
def create_report(screening_id: uuid.UUID, payload: MovementReportPayload, user: User = Depends(current_user), db: Session = Depends(get_db)) -> MovementScreeningResponse:
    if user.role not in {"clinician", "physiotherapist", "sys-admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Clinical review role is required")
    screening = db.get(MovementScreening, screening_id)
    if not screening:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Screening not found")
    screening.report_summary = payload.summary.strip()
    screening.report_generated_at = datetime.now(timezone.utc)
    screening.status = "REPORT_READY"
    db.commit(); db.refresh(screening)
    return _screening_response(screening)


@router.get("/screenings/{screening_id}/report.pdf")
def report_pdf(screening_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    screening = db.get(MovementScreening, screening_id)
    if not screening:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    if user.role in {"athlete", "guardian", "coach", "institution"} and screening.athlete_user_id not in {a.id for a in _visible_athletes(user, db)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not available")
    pdf = build_movement_report_pdf(screening)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=safesport-ai-screening-{screening.athlete_safesport_id}.pdf"})
