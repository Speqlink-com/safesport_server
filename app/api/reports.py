import uuid
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import current_user, verify_csrf
from app.db.session import get_db
from app.models.auth import User
from app.models.care import CareRecord
from app.models.institution import Institution
from app.models.ppe import PPEAssessment
from app.models.reporting import TermReport
from app.schemas.reporting import ReportSummary, TermReportGenerateRequest
from app.services.report_service import build_full_report_pdf, build_term_report_pdf, full_report_data

router = APIRouter(prefix="/reports", tags=["reports"])
STAFF = {"clinician", "physiotherapist", "institution", "coach", "operations", "sys-admin"}


def _institution_id(user: User, db: Session) -> uuid.UUID | None:
    raw = (user.profile_data or {}).get("institution_id") or (user.profile_data or {}).get("organization_id")
    if raw:
        try: return uuid.UUID(str(raw))
        except ValueError: return None
    if user.role == "institution":
        inst = db.scalar(select(Institution).where(Institution.contact_email == user.email))
        return inst.id if inst else None
    return None


def _athletes_in_scope(user: User, db: Session) -> list[User]:
    if user.role == "athlete": return [user]
    if user.role == "guardian":
        try: aid = uuid.UUID(str((user.profile_data or {}).get("athlete_id") or ""))
        except ValueError: return []
        athlete = db.get(User, aid)
        return [athlete] if athlete and athlete.role == "athlete" else []
    stmt = select(User).where(User.role == "athlete", User.is_active.is_(True))
    inst_id = _institution_id(user, db)
    athletes = list(db.scalars(stmt.order_by(User.created_at.desc())).all())
    if user.role in {"institution", "coach"}:
        if not inst_id:
            return []
        athletes = [a for a in athletes if str((a.profile_data or {}).get("organization_id") or (a.profile_data or {}).get("institution_id") or "") == str(inst_id)]
    return athletes if user.role in STAFF else []


def _require_athlete(user: User, db: Session, athlete_id: uuid.UUID) -> User:
    athletes = _athletes_in_scope(user, db)
    athlete = next((a for a in athletes if a.id == athlete_id), None)
    if not athlete: raise HTTPException(status.HTTP_404_NOT_FOUND, "Athlete report not available")
    return athlete


def _summary(report: TermReport) -> ReportSummary:
    return ReportSummary(id=str(report.id), athlete_id=str(report.athlete_user_id), athlete_name=f"{report.athlete.first_name} {report.athlete.last_name}", title=report.title, period_start=report.period_start, period_end=report.period_end, status=report.status, created_at=report.created_at)


@router.get("/athletes")
def report_athletes(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict[str, str]]:
    return [{"id": str(a.id), "name": f"{a.first_name} {a.last_name}", "institution": str((a.profile_data or {}).get("organization_name") or ""), "sport": str((a.profile_data or {}).get("sport_name") or "")} for a in _athletes_in_scope(user, db)]


@router.get("/full/{athlete_id}")
def full_report(athlete_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    athlete = _require_athlete(user, db, athlete_id)
    pdf = build_full_report_pdf(full_report_data(db, athlete))
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=safesport-full-report-{athlete.id}.pdf"})


@router.post("/termly/generate", response_model=list[ReportSummary], dependencies=[Depends(verify_csrf)])
def generate_termly(payload: TermReportGenerateRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[ReportSummary]:
    if user.role != "institution": raise HTTPException(status.HTTP_403_FORBIDDEN, "Institution role is required")
    if payload.period_end < payload.period_start: raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Period end must be after period start")
    inst_id = _institution_id(user, db)
    reports: list[TermReport] = []
    for athlete in _athletes_in_scope(user, db):
        existing = db.scalar(select(TermReport).where(TermReport.athlete_user_id == athlete.id, TermReport.period_start == payload.period_start, TermReport.period_end == payload.period_end))
        if existing:
            reports.append(existing); continue
        records_count = db.scalar(select(CareRecord).where(CareRecord.athlete_user_id == athlete.id).count()) if False else 0
        report = TermReport(institution_id=inst_id, athlete_user_id=athlete.id, title=payload.title.strip() or "Termly athlete progress report", period_start=payload.period_start, period_end=payload.period_end, summary="Institution-generated term summary from SafeSport records.", created_by_user_id=user.id)
        db.add(report); reports.append(report)
    db.commit()
    for r in reports: db.refresh(r)
    return [_summary(r) for r in reports]


@router.get("/termly", response_model=list[ReportSummary])
def termly_reports(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[ReportSummary]:
    athlete_ids = [a.id for a in _athletes_in_scope(user, db)]
    if not athlete_ids: return []
    reports = list(db.scalars(select(TermReport).where(TermReport.athlete_user_id.in_(athlete_ids)).order_by(TermReport.created_at.desc())).unique().all())
    return [_summary(r) for r in reports]


@router.get("/termly/{report_id}")
def termly_report_pdf(report_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    report = db.get(TermReport, report_id)
    if not report: raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    athlete = _require_athlete(user, db, report.athlete_user_id)
    records = list(db.scalars(select(CareRecord).where(CareRecord.athlete_user_id == athlete.id).order_by(CareRecord.created_at.desc())).all())
    assessments = list(db.scalars(select(PPEAssessment).where(PPEAssessment.athlete_user_id == athlete.id).order_by(PPEAssessment.created_at.desc())).all())
    pdf = build_term_report_pdf(report, athlete, records, assessments)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=safesport-term-report-{report.id}.pdf"})


@router.get("/ai-screening-template")
def ai_template() -> dict[str, str]:
    return {"detail": "AI screening report template placeholder. AI screening generation will be completed in the AI phase."}
