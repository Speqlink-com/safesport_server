from io import BytesIO
from textwrap import wrap

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.config import get_settings
from app.models.movement import MovementScreening


def _line(c: canvas.Canvas, text: str, x: float, y: float, size: int = 9, color=colors.HexColor("#334155"), bold: bool = False) -> float:
    c.setFillColor(color)
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.drawString(x, y, text)
    return y - size - 5


def _wrap(c: canvas.Canvas, text: str, x: float, y: float, width: int = 92, size: int = 9) -> float:
    for line in wrap(text or "—", width=width):
        y = _line(c, line, x, y, size=size)
    return y


def build_movement_report_pdf(screening: MovementScreening) -> bytes:
    settings = get_settings()
    buffer = BytesIO()
    page_w, page_h = A4
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"SafeSport Movement Report {screening.athlete_safesport_id}")
    c.setFillColor(colors.HexColor("#ecfdf5")); c.rect(0, page_h - 92, page_w, 92, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#064e3b")); c.setFont("Helvetica-Bold", 18)
    c.drawString(42, page_h - 42, "SafeSport™ AI Movement Screening Report")
    c.setFont("Helvetica", 9); c.drawString(42, page_h - 60, "Decision support only · Final interpretation requires human clinical review")
    c.setFont("Helvetica-Bold", 10); c.drawRightString(page_w - 42, page_h - 42, screening.athlete_safesport_id)
    y = page_h - 120
    ai = screening.ai_result or {}
    clinician = screening.clinician_review or {}
    physio = screening.physio_review or {}
    rows = [
        ("Athlete", screening.athlete_name), ("Sport", screening.sport or "—"), ("Drill", screening.drill.replace("_", " ").title()),
        ("Camera view", screening.camera_view.replace("_", " ").title()), ("Risk signal", str(ai.get("risk_signal") or "Pending")),
        ("Quality", str((ai.get("quality") or {}).get("status") or "Pending")),
    ]
    c.setFillColor(colors.HexColor("#f8fafc")); c.roundRect(42, y - 76, page_w - 84, 88, 10, fill=1, stroke=0)
    col_x = [58, 240, 410]
    row_y = [y - 8, y - 42]
    for index, (label, value) in enumerate(rows):
        x = col_x[index % 3]; yy = row_y[index // 3]
        c.setFillColor(colors.HexColor("#64748b")); c.setFont("Helvetica", 7); c.drawString(x, yy, label.upper())
        c.setFillColor(colors.HexColor("#0f172a")); c.setFont("Helvetica-Bold", 9); c.drawString(x, yy - 14, str(value)[:34])
    y -= 115
    y = _line(c, "AI analysis summary", 42, y, 12, colors.HexColor("#064e3b"), True)
    y = _wrap(c, str(ai.get("summary") or "AI processing has not produced a finalized interpretation yet."), 42, y, 100)
    y -= 8
    y = _line(c, "Key findings", 42, y, 12, colors.HexColor("#064e3b"), True)
    findings = ai.get("findings") or []
    if not findings: findings = ["No finalized movement findings recorded."]
    for item in findings[:4]:
        y = _wrap(c, f"• {item}", 52, y, 96)
    y -= 8
    y = _line(c, "Clinician interpretation", 42, y, 12, colors.HexColor("#064e3b"), True)
    y = _wrap(c, clinician.get("interpretation") or "Awaiting clinician interpretation.", 42, y, 100)
    if physio:
        y -= 8; y = _line(c, "Physiotherapist review", 42, y, 12, colors.HexColor("#064e3b"), True)
        y = _wrap(c, physio.get("interpretation") or "Reviewed by physiotherapy.", 42, y, 100)
    y -= 8; y = _line(c, "Final report summary", 42, y, 12, colors.HexColor("#064e3b"), True)
    y = _wrap(c, screening.report_summary or "No custom report summary has been generated yet.", 42, y, 100)
    c.setFillColor(colors.HexColor("#64748b")); c.setFont("Helvetica", 7)
    c.drawString(42, 32, f"SafeSport contact: {settings.zoho_from_email or 'support@safesport.local'} · Institution contact is maintained in the SafeSport institution profile.")
    c.drawRightString(page_w - 42, 32, "AI risk signal is not a diagnosis or automatic eligibility decision")
    c.showPage(); c.save(); buffer.seek(0)
    return buffer.read()
