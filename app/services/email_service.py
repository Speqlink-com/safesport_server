import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def send(self, recipient: str, subject: str, html: str) -> None:
        if self.settings.email_delivery_mode == "console":
            logger.info("Development email to %s: %s", recipient, subject)
            return
        required = (
            self.settings.zoho_smtp_username,
            self.settings.zoho_smtp_password,
            self.settings.zoho_from_email,
        )
        if not all(required):
            raise RuntimeError("Zoho SMTP credentials are not configured")
        await asyncio.to_thread(self._send_sync, recipient, subject, html)

    def _send_sync(self, recipient: str, subject: str, html: str) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{self.settings.zoho_from_name} <{self.settings.zoho_from_email}>"
        message["To"] = recipient
        message.set_content("Open this SafeSport security email in an HTML-capable email client.")
        message.add_alternative(html, subtype="html")
        with smtplib.SMTP(self.settings.zoho_smtp_host, self.settings.zoho_smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(self.settings.zoho_smtp_username, self.settings.zoho_smtp_password)
            smtp.send_message(message)


email_service = EmailService()

