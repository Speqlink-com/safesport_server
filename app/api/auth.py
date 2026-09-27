import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import current_user, set_csrf_cookie, verify_csrf
from app.core.config import get_settings
from app.db.session import get_db
from app.models.auth import PasswordReset, PendingRegistration, RefreshSession, User
from app.models.institution import Institution
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    OtpRequest,
    PendingRegistrationResponse,
    RegistrationStartRequest,
    ResetPasswordRequest,
    SessionResponse,
    UpdateMeRequest,
    UserResponse,
)
from app.services.auth_service import (
    LOGIN_COOKIE,
    REGISTRATION_COOKIE,
    RESET_COOKIE,
    clear_auth_cookies,
    clear_cookie,
    revoke_refresh_token,
    rotate_refresh_token,
    set_auth_cookies,
    set_http_only_cookie,
)
from app.services.email_service import email_service
from app.services.email_templates import reset_email
from app.services.otp_service import issue_otp, verify_otp
from app.services.security import create_jwt, decode_jwt, hash_password, hash_secret, is_expired, random_token, verify_password

router = APIRouter(prefix="/auth", tags=["authentication"])
settings = get_settings()


def _cookie_subject(request: Request, name: str, token_type: str) -> str:
    token = request.cookies.get(name)
    if not token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This authentication step has expired")
    try:
        return str(decode_jwt(token, token_type)["sub"])
    except (jwt.PyJWTError, KeyError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This authentication step has expired") from exc


@router.get("/csrf", response_model=MessageResponse)
def csrf(response: Response) -> MessageResponse:
    set_csrf_cookie(response)
    return MessageResponse(detail="CSRF cookie initialized")


@router.post("/login", response_model=MessageResponse, dependencies=[Depends(verify_csrf)])
async def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> MessageResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    token = create_jwt(str(user.id), "login", timedelta(minutes=settings.otp_expire_minutes))
    set_http_only_cookie(response, LOGIN_COOKIE, token, settings.otp_expire_minutes * 60, "/api/v1/auth")
    await issue_otp(db, user.email, "login", str(user.id))
    return MessageResponse(detail="Verification code sent")


@router.post("/login/verify", response_model=SessionResponse, dependencies=[Depends(verify_csrf)])
def login_verify(payload: OtpRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> SessionResponse:
    subject_id = _cookie_subject(request, LOGIN_COOKIE, "login")
    verify_otp(db, payload.code, "login", subject_id)
    user = db.get(User, uuid.UUID(subject_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is unavailable")
    set_auth_cookies(response, db, user)
    clear_cookie(response, LOGIN_COOKIE, "/api/v1/auth")
    return SessionResponse(user=UserResponse.model_validate(user))


@router.post("/login/resend", response_model=MessageResponse, dependencies=[Depends(verify_csrf)])
async def login_resend(request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    subject_id = _cookie_subject(request, LOGIN_COOKIE, "login")
    user = db.get(User, uuid.UUID(subject_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This authentication step has expired")
    await issue_otp(db, user.email, "login", subject_id)
    return MessageResponse(detail="A new verification code was sent")


@router.get("/me", response_model=SessionResponse)
def me(user: User = Depends(current_user)) -> SessionResponse:
    return SessionResponse(user=UserResponse.model_validate(user))


@router.put("/me", response_model=SessionResponse, dependencies=[Depends(verify_csrf)])
def update_me(
    payload: UpdateMeRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> SessionResponse:
    user.first_name = payload.first_name.strip()
    user.last_name = payload.last_name.strip()
    profile_data = dict(user.profile_data or {})
    phone = (payload.phone or "").strip()
    if phone:
        profile_data["phone"] = phone
    else:
        profile_data.pop("phone", None)
    user.profile_data = profile_data
    db.commit()
    db.refresh(user)
    return SessionResponse(user=UserResponse.model_validate(user))


@router.post("/refresh", response_model=SessionResponse, dependencies=[Depends(verify_csrf)])
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> SessionResponse:
    user = rotate_refresh_token(request, response, db)
    return SessionResponse(user=UserResponse.model_validate(user))


@router.post("/logout", response_model=MessageResponse, dependencies=[Depends(verify_csrf)])
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> MessageResponse:
    revoke_refresh_token(request, db)
    clear_auth_cookies(response)
    clear_cookie(response, LOGIN_COOKIE, "/api/v1/auth")
    clear_cookie(response, REGISTRATION_COOKIE, "/api/v1/auth")
    return MessageResponse(detail="Signed out")


@router.post("/register/start", response_model=MessageResponse, dependencies=[Depends(verify_csrf)])
async def registration_start(
    payload: RegistrationStartRequest, response: Response, db: Session = Depends(get_db)
) -> MessageResponse:
    email = payload.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    db.execute(delete(PendingRegistration).where(PendingRegistration.email == email))
    profile_data: dict[str, str] = {}
    if payload.role == "athlete":
        try:
            institution_id = uuid.UUID(payload.organization_id or "")
            sport_id = uuid.UUID(payload.sport_id or "")
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Institution or sport is invalid") from exc
        institution = db.get(Institution, institution_id)
        sport = next((item for item in institution.sports if item.id == sport_id), None) if institution else None
        if not institution or not institution.is_active or not sport or not sport.is_active:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The selected institution or sport is unavailable")
        logo_url = institution.logo_path or ""
        profile_data = {
            "date_of_birth": payload.date_of_birth.isoformat() if payload.date_of_birth else "",
            "organization_id": str(institution.id),
            "organization_name": institution.name,
            "organization_logo_url": logo_url,
            "sport_id": str(sport.id),
            "sport_name": sport.name,
        }
    else:
        profile_data = {
            "relationship": payload.relationship or "",
            "athlete_id": payload.athlete_id or "",
        }
    pending = PendingRegistration(
        email=email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        role=payload.role,
        profile_data=profile_data,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    cookie = create_jwt(str(pending.id), "registration", timedelta(minutes=30))
    set_http_only_cookie(response, REGISTRATION_COOKIE, cookie, 30 * 60, "/api/v1/auth")
    await issue_otp(db, email, "registration", str(pending.id))
    return MessageResponse(detail="Verification code sent")


def _pending_registration(request: Request, db: Session) -> PendingRegistration:
    pending_id = _cookie_subject(request, REGISTRATION_COOKIE, "registration")
    pending = db.get(PendingRegistration, uuid.UUID(pending_id))
    if not pending or is_expired(pending.expires_at):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Registration has expired")
    return pending


@router.post("/register/verify", response_model=MessageResponse, dependencies=[Depends(verify_csrf)])
def registration_verify(payload: OtpRequest, request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    pending = _pending_registration(request, db)
    verify_otp(db, payload.code, "registration", str(pending.id))
    pending.is_verified = True
    db.commit()
    return MessageResponse(detail="Email verified")


@router.post("/register/resend", response_model=MessageResponse, dependencies=[Depends(verify_csrf)])
async def registration_resend(request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    pending = _pending_registration(request, db)
    await issue_otp(db, pending.email, "registration", str(pending.id))
    return MessageResponse(detail="A new verification code was sent")


@router.get("/register/current", response_model=PendingRegistrationResponse)
def registration_current(request: Request, db: Session = Depends(get_db)) -> PendingRegistrationResponse:
    pending = _pending_registration(request, db)
    return PendingRegistrationResponse(
        email=pending.email,
        first_name=pending.first_name,
        last_name=pending.last_name,
        role=pending.role,
        profile_data=pending.profile_data,
        is_verified=pending.is_verified,
    )


@router.post("/register/complete", response_model=SessionResponse, dependencies=[Depends(verify_csrf)])
def registration_complete(request: Request, response: Response, db: Session = Depends(get_db)) -> SessionResponse:
    pending = _pending_registration(request, db)
    if not pending.is_verified:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email verification is required")
    user = User(
        email=pending.email,
        password_hash=pending.password_hash,
        first_name=pending.first_name,
        last_name=pending.last_name,
        role=pending.role,
        profile_data=pending.profile_data,
    )
    db.add(user)
    db.delete(pending)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists") from exc
    db.refresh(user)
    set_auth_cookies(response, db, user)
    clear_cookie(response, REGISTRATION_COOKIE, "/api/v1/auth")
    return SessionResponse(user=UserResponse.model_validate(user))


@router.post("/password/forgot", response_model=MessageResponse, dependencies=[Depends(verify_csrf)])
async def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> MessageResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower(), User.is_active.is_(True)))
    if user:
        db.execute(
            update(PasswordReset)
            .where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
            .values(used_at=datetime.now(timezone.utc))
        )
        raw_token = random_token()
        db.add(
            PasswordReset(
                user_id=user.id,
                token_hash=hash_secret(raw_token),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_expire_minutes),
            )
        )
        db.commit()
        reset_url = f"{settings.backend_public_url.rstrip('/')}/api/v1/auth/password/reset/consume?code={quote(raw_token)}"
        subject, html = reset_email(reset_url)
        await email_service.send(user.email, subject, html)
    return MessageResponse(detail="If that account exists, password reset instructions were sent")


@router.get("/password/reset/consume")
def consume_reset_link(code: str, db: Session = Depends(get_db)) -> RedirectResponse:
    reset = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == hash_secret(code)))
    target = f"{settings.frontend_url.rstrip('/')}/account/reset-pasword"
    if not reset or reset.used_at or is_expired(reset.expires_at):
        return RedirectResponse(f"{target}?error=expired")
    response = RedirectResponse(target)
    cookie = create_jwt(str(reset.id), "password_reset", timedelta(minutes=settings.password_reset_expire_minutes))
    set_http_only_cookie(response, RESET_COOKIE, cookie, settings.password_reset_expire_minutes * 60, "/api/v1/auth")
    return response


@router.post("/password/reset", response_model=MessageResponse, dependencies=[Depends(verify_csrf)])
def reset_password(
    payload: ResetPasswordRequest, request: Request, response: Response, db: Session = Depends(get_db)
) -> MessageResponse:
    reset_id = _cookie_subject(request, RESET_COOKIE, "password_reset")
    reset = db.get(PasswordReset, uuid.UUID(reset_id))
    now = datetime.now(timezone.utc)
    if not reset or reset.used_at or is_expired(reset.expires_at):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The password reset link is invalid or expired")
    user = db.get(User, reset.user_id)
    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The password reset link is invalid or expired")
    user.password_hash = hash_password(payload.password)
    reset.used_at = now
    db.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.commit()
    clear_cookie(response, RESET_COOKIE, "/api/v1/auth")
    clear_auth_cookies(response)
    return MessageResponse(detail="Password reset successfully")
