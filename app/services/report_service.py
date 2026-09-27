from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from urllib.request import urlopen

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
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


def _ensure_space(c: canvas.Canvas, y: float, section: str | None = None) -> float:
    if y < 35 * mm:
        c.showPage()
        y = _header(c, "SafeSport Full Athlete Report", "continued")
        if section:
            y = _section(c, section, y)
    return y


def _payload(assessment: PPEAssessment) -> dict:
    data = {}
    data.update(assessment.history_payload or {})
    data.update(assessment.clinical_payload or {})
    return data


def _dict_rows(c: canvas.Canvas, title: str, values: dict, x: float, y: float, width: float) -> float:
    if not values:
        c.setFont("Helvetica", 9); c.setFillColor(colors.HexColor("#64748B")); c.drawString(x, y, f"No {title.lower()} recorded.")
        return y - 7 * mm
    c.setFont("Helvetica-Bold", 9); c.setFillColor(colors.HexColor("#0F172A")); c.drawString(x, y, title); y -= 5 * mm
    for key, value in values.items():
        y = _ensure_space(c, y, title)
        if isinstance(value, dict):
            value = "; ".join(f"{k}: {v}" for k, v in value.items() if v not in (None, ""))
        c.setFont("Helvetica-Bold", 8); c.setFillColor(colors.HexColor("#334155")); c.drawString(x, y, str(key)[:70])
        y -= 4 * mm
        c.setFont("Helvetica", 8); c.setFillColor(colors.HexColor("#475569")); y = _wrap(c, str(value or "—"), x + 3 * mm, y, width - 3 * mm, 10)
    return y - 2 * mm


def _list_rows(c: canvas.Canvas, title: str, values: list, x: float, y: float, width: float) -> float:
    c.setFont("Helvetica-Bold", 9); c.setFillColor(colors.HexColor("#0F172A")); c.drawString(x, y, title); y -= 5 * mm
    if not values:
        c.setFont("Helvetica", 8); c.setFillColor(colors.HexColor("#64748B")); c.drawString(x, y, "None recorded.")
        return y - 7 * mm
    for index, value in enumerate(values, 1):
        y = _ensure_space(c, y, title)
        text = value if isinstance(value, str) else "; ".join(f"{k}: {v}" for k, v in dict(value).items() if v not in (None, ""))
        c.setFont("Helvetica", 8); c.setFillColor(colors.HexColor("#475569")); y = _wrap(c, f"{index}. {text}", x, y, width, 10)
    return y - 2 * mm


def _table_doc_header(canvas_obj: canvas.Canvas, doc, title: str, subtitle: str) -> None:
    w, h = A4
    canvas_obj.saveState()
    canvas_obj.setFillColor(colors.HexColor("#EAF7F2"))
    canvas_obj.rect(0, h - 34 * mm, w, 34 * mm, fill=1, stroke=0)
    logo = _logo()
    if logo:
        canvas_obj.drawImage(logo, 18 * mm, h - 23 * mm, width=35 * mm, height=13 * mm, mask="auto", preserveAspectRatio=True)
    canvas_obj.setFillColor(colors.HexColor("#0F172A"))
    canvas_obj.setFont("Helvetica-Bold", 16)
    canvas_obj.drawString(18 * mm, h - 29 * mm, title)
    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColor(colors.HexColor("#475569"))
    canvas_obj.drawRightString(w - 18 * mm, h - 17 * mm, subtitle)
    canvas_obj.setFont("Helvetica", 7)
    canvas_obj.drawCentredString(w / 2, 11 * mm, f"SafeSport confidential athlete report · page {doc.page}")
    canvas_obj.restoreState()


def _cell(value: object) -> Paragraph:
    styles = getSampleStyleSheet()
    style = ParagraphStyle("SafeSportCell", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.4, leading=9.5, textColor=colors.HexColor("#334155"))
    text = str(value if value not in (None, "") else "—")
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
    return Paragraph(text, style)


def _heading(text: str) -> Paragraph:
    style = ParagraphStyle("SafeSportHeading", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#0F766E"), spaceBefore=8, spaceAfter=6)
    return Paragraph(text, style)


def _make_table(rows: list[list[object]], widths: list[float] | None = None) -> Table:
    table = Table([[ _cell(item) for item in row] for row in rows], colWidths=widths, repeatRows=1 if rows else 0, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ECFDF5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0F766E")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.4),
        ("LEADING", (0, 0), (-1, -1), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _kv_table(items: list[tuple[str, object]]) -> Table:
    return _make_table([["Field", "Value"], *items], [48 * mm, 125 * mm])


def _dict_table(title: str, values: dict, key_label = "Item", value_label = "Value") -> list[object]:
    rows: list[list[object]] = [[key_label, value_label]]
    if values:
        for key, value in values.items():
            if isinstance(value, dict):
                value = "\n".join(f"{k}: {v}" for k, v in value.items() if v not in (None, ""))
            rows.append([str(key), value or "—"])
    else:
        rows.append(["—", "None recorded"])
    return [_heading(title), _make_table(rows, [58 * mm, 115 * mm]), Spacer(1, 6)]


def _list_table(title: str, values: list) -> list[object]:
    rows: list[list[object]] = [["#", "Details"]]
    if values:
        for index, value in enumerate(values, 1):
            if isinstance(value, dict):
                value = "\n".join(f"{k}: {v}" for k, v in value.items() if v not in (None, ""))
            rows.append([index, value or "—"])
    else:
        rows.append(["—", "None recorded"])
    return [_heading(title), _make_table(rows, [14 * mm, 159 * mm]), Spacer(1, 6)]


def build_full_report_pdf(data: AthleteReportData) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=42 * mm, bottomMargin=18 * mm)
    story: list[object] = []
    athlete = data.athlete
    story.append(_heading("Basic details"))
    story.append(_kv_table([
        ("Athlete", _name(athlete)),
        ("Email", athlete.email),
        ("Institution / club", _profile(athlete, "organization_name")),
        ("Sport", _profile(athlete, "sport_name")),
        ("Date of birth", _profile(athlete, "date_of_birth")),
        ("Report generated", "2026-09-27"),
    ]))
    story.append(Spacer(1, 8))
    story.append(_heading("Consent records"))
    story.append(_make_table(
        [["Version", "Clinical", "Video", "Research", "Assent", "Signer", "Recorded"]] +
        ([[c.version, c.clinical, c.video, c.research, c.assent, c.signer, (c.consented_at or c.updated_at)] for c in data.consents] or [["—", "No consent record", "—", "—", "—", "—", "—"]]),
        [28 * mm, 25 * mm, 18 * mm, 22 * mm, 18 * mm, 35 * mm, 27 * mm],
    ))
    for index, item in enumerate(data.assessments, 1):
        payload = _payload(item)
        story.append(PageBreak())
        story.append(_heading(f"PPE assessment {index}"))
        story.append(_kv_table([
            ("Date", item.created_at.date()),
            ("Status", item.status),
            ("History submitted", item.history_submitted),
            ("Reviewed", item.reviewed),
            ("Finalized", item.finalized),
            ("Decision", item.decision),
            ("Restrictions", item.restrictions or "None"),
            ("Plan", item.plan or "None"),
            ("Review date", item.review_date or "—"),
            ("Rationale", item.rationale or "—"),
            ("Clinician signature", item.signature or "—"),
            ("Certificate", item.certificate_code or "—"),
            ("Physio status", item.physio_status),
            ("Physio note", item.physio_note or "—"),
        ]))
        story.extend(_dict_table("Health history answers", payload.get("historyAnswers") or payload.get("history") or {}, "Question", "Answer"))
        story.extend(_dict_table("Health follow-up details", payload.get("historyDetails") or payload.get("followups") or {}, "Question", "Details"))
        story.extend(_dict_table("Clinician resolutions", payload.get("historyResolutions") or {}, "Question", "Resolution"))
        story.extend(_list_table("Injury history", payload.get("injuries") or []))
        story.extend(_dict_table("Concussion history", payload.get("concussion") or {}, "Field", "Response"))
        story.extend(_dict_table("Physical exam", payload.get("exam") or {}, "Domain", "Finding"))
        story.extend(_dict_table("Exam notes", payload.get("examNotes") or {}, "Domain", "Notes"))
        story.extend(_dict_table("Musculoskeletal baseline", payload.get("baseline") or {}, "Domain", "Finding"))
        story.extend(_dict_table("Baseline notes", payload.get("baselineNotes") or {}, "Domain", "Notes"))
        story.extend(_dict_table("Vitals", payload.get("vitals") or {}, "Vital", "Value"))
        story.append(_heading("Sport-specific notes"))
        story.append(_make_table([["Notes"], [payload.get("sportNotes") or "—"]], [173 * mm]))
        story.extend(_dict_table("Care review", payload.get("careReview") or {}, "Field", "Details"))
    if not data.assessments:
        story.append(_heading("PPE assessments")); story.append(_make_table([["Status"], ["No PPE assessments recorded."]], [173 * mm]))
    story.append(PageBreak())
    story.append(_heading("Health, incident, rehabilitation and document records"))
    story.append(_make_table(
        [["Date", "Type", "Title", "Status", "Assigned", "Notes / outcome"]] +
        ([[r.date or r.created_at.date(), r.collection, r.title, r.status, r.assigned or "—", r.notes or r.outcome or r.coordination or "—"] for r in data.records] or [["—", "—", "No care records recorded", "—", "—", "—"]]),
        [23 * mm, 24 * mm, 38 * mm, 23 * mm, 30 * mm, 35 * mm],
    ))
    doc.build(story, onFirstPage=lambda c, d: _table_doc_header(c, d, "SafeSport Full Athlete Report", "Confidential health record"), onLaterPages=lambda c, d: _table_doc_header(c, d, "SafeSport Full Athlete Report", "continued"))
    return buf.getvalue()


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
