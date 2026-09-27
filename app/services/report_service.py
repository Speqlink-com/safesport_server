from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from urllib.request import urlopen

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.auth import User
from app.models.care import CareRecord
from app.models.ppe import PPEAssessment, PPEConsent
from app.models.reporting import TermReport


@dataclass
class AthleteReportData:
    athlete: User
    assessments: list[PPEAssessment]
    consents: list[PPEConsent]
    records: list[CareRecord]


def _logo() -> ImageReader | None:
    try:
        return ImageReader(BytesIO(urlopen(get_settings().safesport_logo_url, timeout=6).read()))
    except Exception:
        return None


def _name(user: User) -> str:
    return f"{user.first_name} {user.last_name}".strip()


def _profile(user: User, key: str, fallback: str = "—") -> str:
    value = (user.profile_data or {}).get(key)
    return str(value) if value else fallback


def _wrap(c: canvas.Canvas, text: str, x: float, y: float, width: float, leading: float = 12) -> float:
    words = str(text or "—").split()
    line = ""
    for word in words or ["—"]:
        candidate = f"{line} {word}".strip()
        if c.stringWidth(candidate, "Helvetica", 9) <= width:
            line = candidate
        else:
            c.drawString(x, y, line)
            y -= leading
            line = word
    c.drawString(x, y, line)
    return y - leading


def _header(c: canvas.Canvas, title: str, subtitle: str) -> float:
    w, h = A4
    c.setFillColor(colors.HexColor("#EAF7F2"))
    c.rect(0, h - 42 * mm, w, 42 * mm, fill=1, stroke=0)
    logo = _logo()
    if logo:
        c.drawImage(logo, 18 * mm, h - 28 * mm, width=35 * mm, height=13 * mm, mask="auto", preserveAspectRatio=True)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", 18)
    c.drawString(18 * mm, h - 34 * mm, title)
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawRightString(w - 18 * mm, h - 18 * mm, subtitle)
    return h - 52 * mm


def _section(c: canvas.Canvas, title: str, y: float) -> float:
    if y < 35 * mm:
        c.showPage(); y = _header(c, "SafeSport Athlete Report", "continued")
    c.setFillColor(colors.HexColor("#0F766E"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(18 * mm, y, title)
    c.setStrokeColor(colors.HexColor("#CCFBF1"))
    c.line(18 * mm, y - 3, 192 * mm, y - 3)
    return y - 9 * mm


def build_full_report_pdf(data: AthleteReportData) -> bytes:
    buf = BytesIO(); c = canvas.Canvas(buf, pagesize=A4); w, _ = A4
    y = _header(c, "SafeSport Full Athlete Report", "Confidential health record")
    athlete = data.athlete
    fields = [
        ("Athlete", _name(athlete)), ("Email", athlete.email), ("Institution", _profile(athlete, "organization_name")),
        ("Sport", _profile(athlete, "sport_name")), ("Date of birth", _profile(athlete, "date_of_birth")),
        ("Generated", "2026-09-27"),
    ]
    y = _section(c, "Basic details", y)
    for i, (label, value) in enumerate(fields):
        x = 18 * mm if i % 2 == 0 else 108 * mm
        if i % 2 == 0 and i: y -= 12 * mm
        c.setFillColor(colors.HexColor("#64748B")); c.setFont("Helvetica", 8); c.drawString(x, y, label.upper())
        c.setFillColor(colors.HexColor("#0F172A")); c.setFont("Helvetica-Bold", 10); c.drawString(x, y - 11, str(value))
    y -= 24 * mm
    y = _section(c, "PPE assessments", y)
    for item in data.assessments:
        c.setFont("Helvetica-Bold", 9); c.setFillColor(colors.HexColor("#0F172A"))
        c.drawString(20 * mm, y, f"{item.created_at.date()} · {item.status} · {item.decision}")
        y -= 5 * mm; c.setFont("Helvetica", 9); c.setFillColor(colors.HexColor("#334155"))
        y = _wrap(c, f"Restrictions: {item.restrictions or 'None'} | Plan: {item.plan or 'None'} | Review: {item.review_date or '—'}", 20 * mm, y, w - 40 * mm)
    if not data.assessments: c.drawString(20 * mm, y, "No PPE assessments recorded."); y -= 8 * mm
    y = _section(c, "Health, incident, rehabilitation and document records", y)
    for record in data.records:
        if y < 35 * mm: c.showPage(); y = _header(c, "SafeSport Full Athlete Report", "continued"); y = _section(c, "Health records continued", y)
        c.setFont("Helvetica-Bold", 9); c.setFillColor(colors.HexColor("#0F172A"))
        c.drawString(20 * mm, y, f"{record.date or record.created_at.date()} · {record.collection} · {record.title} · {record.status}")
        y -= 5 * mm; c.setFont("Helvetica", 9); c.setFillColor(colors.HexColor("#334155"))
        y = _wrap(c, record.notes or record.outcome or record.coordination or "No narrative recorded.", 20 * mm, y, w - 40 * mm)
    if not data.records: c.drawString(20 * mm, y, "No care records recorded.")
    c.showPage(); c.save(); return buf.getvalue()


def build_term_report_pdf(report: TermReport, athlete: User, records: list[CareRecord], assessments: list[PPEAssessment]) -> bytes:
    buf = BytesIO(); c = canvas.Canvas(buf, pagesize=A4); w, h = A4
    y = _header(c, report.title, f"{report.period_start} to {report.period_end}")
    c.setFont("Helvetica-Bold", 16); c.setFillColor(colors.HexColor("#0F172A")); c.drawString(18*mm, y, _name(athlete)); y -= 8*mm
    c.setFont("Helvetica", 10); c.setFillColor(colors.HexColor("#475569")); c.drawString(18*mm, y, f"{_profile(athlete,'organization_name')} · {_profile(athlete,'sport_name')}"); y -= 14*mm
    latest = assessments[0] if assessments else None
    metrics = [("PPE", latest.status if latest else "not recorded"), ("Eligibility", latest.decision if latest else "pending"), ("Care records", str(len(records))), ("Incidents", str(len([r for r in records if r.collection=='incidents'])))]
    for i,(label,value) in enumerate(metrics):
        x = 18*mm + (i%2)*88*mm; yy = y - (i//2)*24*mm
        c.setFillColor(colors.HexColor("#F8FAFC")); c.roundRect(x, yy-15*mm, 78*mm, 19*mm, 5, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#64748B")); c.setFont("Helvetica", 8); c.drawString(x+5*mm, yy-3*mm, label.upper())
        c.setFillColor(colors.HexColor("#0F172A")); c.setFont("Helvetica-Bold", 12); c.drawString(x+5*mm, yy-10*mm, str(value).replace('_',' '))
    y -= 58*mm
    y = _section(c, "Term summary", y)
    summary = report.summary or "Progress summary generated from SafeSport records for the selected period. Continue routine monitoring and update records after incidents, rehabilitation sessions and return-to-play reviews."
    y = _wrap(c, summary, 20*mm, y, w-40*mm, 13)
    y = _section(c, "Recent period records", y-5*mm)
    for record in records[:8]:
        c.setFont("Helvetica-Bold",9); c.setFillColor(colors.HexColor("#0F172A")); c.drawString(20*mm,y,f"{record.date or record.created_at.date()} · {record.title} · {record.status}"); y-=5*mm
        c.setFont("Helvetica",8); c.setFillColor(colors.HexColor("#475569")); y=_wrap(c, record.notes or "No notes", 20*mm, y, w-40*mm, 10)
    c.setFont("Helvetica",8); c.setFillColor(colors.HexColor("#64748B")); c.drawString(18*mm, 15*mm, "SafeSport term report · one-page institutional summary")
    c.showPage(); c.save(); return buf.getvalue()


def full_report_data(db: Session, athlete: User) -> AthleteReportData:
    assessments=list(db.scalars(select(PPEAssessment).where(PPEAssessment.athlete_user_id==athlete.id).order_by(PPEAssessment.created_at.desc())).all())
    consents=list(db.scalars(select(PPEConsent).where(PPEConsent.athlete_user_id==athlete.id)).all())
    records=list(db.scalars(select(CareRecord).where(CareRecord.athlete_user_id==athlete.id).order_by(CareRecord.created_at.desc())).all())
    return AthleteReportData(athlete, assessments, consents, records)
