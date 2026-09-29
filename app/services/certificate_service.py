from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from urllib.request import urlopen

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

from app.core.config import get_settings
from app.models.auth import User
from app.models.ppe import PPEAssessment

DEFAULT_LOGO_URL = "https://res.cloudinary.com/dfyqn0c1t/image/upload/v1790532798/safesport_1_roaybx.png"


@dataclass(frozen=True)
class CertificateContext:
    athlete_name: str
    athlete_id: str
    institution: str
    institution_logo_url: str | None
    sport: str
    assessment_date: str
    decision: str
    restrictions: str
    monitoring: str
    review_date: str
    clinician_signature: str
    verification_code: str
    verification_url: str


def _safe(value: object, fallback: str = "—") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _image(url: str | None) -> ImageReader | None:
    if not url:
        return None
    try:
        with urlopen(url, timeout=6) as response:  # nosec B310 - configured logo URLs only, prototype certificate rendering
            return ImageReader(BytesIO(response.read()))
    except Exception:
        return None


def _draw_text(c: canvas.Canvas, text: str, x: float, y: float, size: int, color=colors.HexColor("#0f172a"), font: str = "Helvetica", max_width: float | None = None) -> float:
    c.setFillColor(color)
    c.setFont(font, size)
    if max_width and stringWidth(text, font, size) > max_width:
        while text and stringWidth(text + "…", font, size) > max_width:
            text = text[:-1]
        text = text + "…"
    c.drawString(x, y, text)
    return y - size - 7


def _draw_signature_mark(c: canvas.Canvas, name: str, x: float, y: float) -> None:
    c.saveState()
    c.setStrokeColor(colors.HexColor("#0f172a"))
    c.setLineWidth(1.7)
    cursor = x
    for index, char in enumerate(name[:24]):
        if char == " ":
            cursor += 9
            continue
        height = 9 + (ord(char) % 11)
        width = 7 + (ord(char) % 6)
        baseline = y + ((index % 3) - 1) * 1.6
        path = c.beginPath()
        path.moveTo(cursor, baseline)
        path.curveTo(cursor + width * 0.25, baseline + height, cursor + width * 0.7, baseline - height * 0.35, cursor + width, baseline + height * 0.25)
        c.drawPath(path, stroke=1, fill=0)
        cursor += width * 0.82
    path = c.beginPath()
    path.moveTo(x - 4, y - 5)
    path.curveTo(x + 52, y - 13, x + 138, y - 10, x + 204, y - 2)
    c.drawPath(path, stroke=1, fill=0)
    c.restoreState()


def _draw_grid(c: canvas.Canvas, width: float, height: float) -> None:
    c.saveState()
    c.setStrokeColor(colors.HexColor("#e8f1ff"))
    c.setLineWidth(0.25)
    gap = 28
    x = 0
    while x < width:
        c.line(x, 0, x, height)
        x += gap
    y = 0
    while y < height:
        c.line(0, y, width, y)
        y += gap
    c.restoreState()


def certificate_context(athlete: User, assessment: PPEAssessment) -> CertificateContext:
    settings = get_settings()
    profile = dict(athlete.profile_data or {})
    code = assessment.certificate_code or f"SAFE-{str(assessment.id)[:8].upper()}"
    verify_url = f"{settings.backend_public_url.rstrip()}/api/v1/ppe/certificates/verify/{code}"
    return CertificateContext(
        athlete_name=f"{athlete.first_name} {athlete.last_name}",
        athlete_id=athlete.safesport_id,
        institution=_safe(profile.get("organization_name")),
        institution_logo_url=profile.get("organization_logo_url") or profile.get("logo_url"),
        sport=_safe(profile.get("sport_name")),
        assessment_date=assessment.created_at.date().isoformat(),
        decision=assessment.decision.replace("_", " ").title(),
        restrictions=_safe(assessment.restrictions, "None specified"),
        monitoring=_safe(assessment.plan, "None specified"),
        review_date=assessment.review_date.isoformat() if assessment.review_date else "—",
        clinician_signature=_safe(assessment.signature),
        verification_code=code,
        verification_url=verify_url,
    )


def build_certificate_pdf(context: CertificateContext) -> bytes:
    settings = get_settings()
    buffer = BytesIO()
    page_width, page_height = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=(page_width, page_height))
    c.setTitle(f"SafeSport Certificate {context.verification_code}")
    c.setAuthor("SafeSport")
    c.setSubject("PPE completion and onboarding participation certificate")

    margin = 34
    c.setFillColor(colors.HexColor("#f8fbff"))
    c.rect(0, 0, page_width, page_height, stroke=0, fill=1)
    _draw_grid(c, page_width, page_height)

    c.saveState()
    c.setFillColor(colors.HexColor("#effbe9"))
    c.circle(page_width - 40, page_height + 20, 190, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#eef6ff"))
    c.circle(40, -20, 160, stroke=0, fill=1)
    c.restoreState()

    c.setStrokeColor(colors.HexColor("#b7e9a6"))
    c.setLineWidth(2)
    c.roundRect(margin, margin, page_width - margin * 2, page_height - margin * 2, 26, stroke=1, fill=0)
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(1)
    c.roundRect(margin + 8, margin + 8, page_width - (margin + 8) * 2, page_height - (margin + 8) * 2, 20, stroke=1, fill=0)

    logo = _image(settings.safesport_logo_url or DEFAULT_LOGO_URL)
    if logo:
        c.drawImage(logo, margin + 28, page_height - margin - 68, width=118, height=44, preserveAspectRatio=True, mask="auto")

    club_logo = _image(context.institution_logo_url)
    if club_logo:
        c.setFillColor(colors.white)
        c.roundRect(page_width - margin - 112, page_height - margin - 82, 74, 62, 14, stroke=0, fill=1)
        c.drawImage(club_logo, page_width - margin - 103, page_height - margin - 74, width=56, height=46, preserveAspectRatio=True, mask="auto")


    title_y = page_height - 150
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(page_width / 2, title_y + 50, "SAFESPORT DIGITAL CERTIFICATE")
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(page_width / 2, title_y + 10, "PPE Completion & Onboarding")
    c.setFont("Helvetica", 13)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawCentredString(page_width / 2, title_y - 18, "Minimum-necessary participation summary for sport onboarding")

    card_x = margin + 42
    card_y = margin + 116
    card_w = page_width - margin * 2 - 84
    card_h = 210
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.roundRect(card_x, card_y, card_w, card_h, 20, stroke=1, fill=1)

    left_x = card_x + 30
    y = card_y + card_h - 42
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawString(left_x, y, "CERTIFIED ATHLETE")
    y -= 34
    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawString(left_x, y, context.athlete_name)
    y -= 28
    c.setFont("Helvetica", 12)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(left_x, y, f"Athlete ID: {context.athlete_id}")
    y -= 24
    c.drawString(left_x, y, f"Institution / club: {context.institution}")
    y -= 24
    c.drawString(left_x, y, f"Sport: {context.sport}")

    right_x = card_x + card_w * 0.58
    y = card_y + card_h - 48
    for label, value in [
        ("Eligibility", context.decision),
        ("Assessment date", context.assessment_date),
        ("Review date", context.review_date),
        ("Restrictions", context.restrictions),
        ("Monitoring", context.monitoring),
    ]:
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(colors.HexColor("#64748b"))
        c.drawString(right_x, y, label.upper())
        y -= 14
        y = _draw_text(c, value, right_x, y, 11, colors.HexColor("#0f172a"), "Helvetica", max_width=card_x + card_w - right_x - 20)
        y -= 2

    sign_y = margin + 72
    c.setStrokeColor(colors.HexColor("#0f172a"))
    c.setLineWidth(0.8)
    c.line(margin + 58, sign_y, margin + 260, sign_y)
    _draw_signature_mark(c, context.clinician_signature, margin + 66, sign_y + 17)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawString(margin + 58, sign_y - 16, "SIGNING CLINICIAN")
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawString(margin + 58, sign_y - 31, context.clinician_signature)

    qr_code = qr.QrCodeWidget(context.verification_url)
    drawing = Drawing(78, 78, transform=[78.0 / qr_code.getBounds()[2], 0, 0, 78.0 / qr_code.getBounds()[3], 0, 0])
    drawing.add(qr_code)
    renderPDF.draw(drawing, c, page_width - margin - 128, margin + 54)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawRightString(page_width - margin - 40, margin + 38, context.verification_code)
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawRightString(page_width - margin - 40, margin + 24, "Scan QR or verify certificate code")

    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawCentredString(page_width / 2, margin + 16, "This certificate excludes clinical history, examination notes, mental-health data and other confidential medical details.")
    c.showPage()
    c.save()
    return buffer.getvalue()
