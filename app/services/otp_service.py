from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.auth import OtpChallenge
from app.services.email_service import email_service
from app.services.email_templates import otp_email
from app.services.security import hash_secret, is_expired, random_otp

settings = get_settings()


async def issue_otp(db: Session, email: str, purpose: str, subject_id: str) -> None:
    db.execute(
        update(OtpChallenge)
        .where(OtpChallenge.purpose == purpose, OtpChallenge.subject_id == subject_id, OtpChallenge.consumed.is_(False))
        .values(consumed=True)
    )
    code = random_otp()
    db.add(
        OtpChallenge(
            email=email,
            purpose=purpose,
            subject_id=subject_id,
            code_hash=hash_secret(code),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expire_minutes),
        )
    )
    db.commit()
    if settings.email_delivery_mode == "console":
        print(f"Development OTP for {email} ({purpose}): {code}", flush=True)
    subject, html = otp_email(code, purpose)
    await email_service.send(email, subject, html)


def verify_otp(db: Session, code: str, purpose: str, subject_id: str) -> None:
    challenge = db.scalar(
        select(OtpChallenge)
        .where(OtpChallenge.purpose == purpose, OtpChallenge.subject_id == subject_id, OtpChallenge.consumed.is_(False))
        .order_by(OtpChallenge.created_at.desc())
    )
    if not challenge or is_expired(challenge.expires_at) or challenge.attempts >= 5:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The verification code is invalid or expired")
    challenge.attempts += 1
    if not __import__("hmac").compare_digest(challenge.code_hash, hash_secret(code)):
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The verification code is invalid or expired")
    challenge.consumed = True
    db.commit()
