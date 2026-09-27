import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.auth import RefreshSession, User
from app.services.security import create_jwt, decode_jwt, hash_secret, is_expired, new_jti

settings = get_settings()
ACCESS_COOKIE = "safesport_access"
REFRESH_COOKIE = "safesport_refresh"
LOGIN_COOKIE = "safesport_login"
REGISTRATION_COOKIE = "safesport_registration"
RESET_COOKIE = "safesport_password_reset"
CSRF_COOKIE = "safesport_csrf"


def _cookie_options(path: str = "/") -> dict[str, object]:
    return {
        "httponly": True,
        "secure": settings.secure_cookies,
        "samesite": settings.cookie_samesite,
        "domain": settings.cookie_domain,
        "path": path,
    }


def set_http_only_cookie(response: Response, name: str, value: str, max_age: int, path: str = "/") -> None:
    response.set_cookie(name, value, max_age=max_age, **_cookie_options(path))


def clear_cookie(response: Response, name: str, path: str = "/") -> None:
    response.delete_cookie(
        name,
        path=path,
        domain=settings.cookie_domain,
        secure=settings.secure_cookies,
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def set_auth_cookies(response: Response, db: Session, user: User) -> None:
    access_seconds = settings.access_token_expire_minutes * 60
    refresh_seconds = settings.refresh_token_expire_days * 24 * 60 * 60
    access = create_jwt(str(user.id), "access", timedelta(seconds=access_seconds))
    jti = new_jti()
    refresh = create_jwt(str(user.id), "refresh", timedelta(seconds=refresh_seconds), jti)
    db.add(
        RefreshSession(
            user_id=user.id,
            jti_hash=hash_secret(jti),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=refresh_seconds),
        )
    )
    db.commit()
    set_http_only_cookie(response, ACCESS_COOKIE, access, access_seconds)
    set_http_only_cookie(response, REFRESH_COOKIE, refresh, refresh_seconds, "/api/v1/auth")


def clear_auth_cookies(response: Response) -> None:
    clear_cookie(response, ACCESS_COOKIE)
    clear_cookie(response, REFRESH_COOKIE, "/api/v1/auth")


def get_access_user(request: Request, db: Session) -> User:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    try:
        payload = decode_jwt(token, "access")
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is invalid or expired") from exc
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is invalid or expired")
    return user


def rotate_refresh_token(request: Request, response: Response, db: Session) -> User:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh session is missing")
    try:
        payload = decode_jwt(token, "refresh")
        user_id = uuid.UUID(payload["sub"])
        jti_hash = hash_secret(payload["jti"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        clear_auth_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh session is invalid or expired") from exc
    session = db.scalar(select(RefreshSession).where(RefreshSession.jti_hash == jti_hash))
    now = datetime.now(timezone.utc)
    if not session or session.revoked_at or is_expired(session.expires_at):
        if session:
            db.execute(
                update(RefreshSession)
                .where(RefreshSession.user_id == session.user_id, RefreshSession.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            db.commit()
        clear_auth_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh session is invalid or expired")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        clear_auth_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh session is invalid or expired")
    session.revoked_at = now
    replacement_jti = new_jti()
    session.replaced_by_hash = hash_secret(replacement_jti)
    access_seconds = settings.access_token_expire_minutes * 60
    refresh_seconds = settings.refresh_token_expire_days * 24 * 60 * 60
    db.add(
        RefreshSession(
            user_id=user.id,
            jti_hash=session.replaced_by_hash,
            expires_at=now + timedelta(seconds=refresh_seconds),
        )
    )
    db.commit()
    set_http_only_cookie(
        response,
        ACCESS_COOKIE,
        create_jwt(str(user.id), "access", timedelta(seconds=access_seconds)),
        access_seconds,
    )
    set_http_only_cookie(
        response,
        REFRESH_COOKIE,
        create_jwt(str(user.id), "refresh", timedelta(seconds=refresh_seconds), replacement_jti),
        refresh_seconds,
        "/api/v1/auth",
    )
    return user


def revoke_refresh_token(request: Request, db: Session) -> None:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        return
    try:
        payload = decode_jwt(token, "refresh")
        jti_hash = hash_secret(payload["jti"])
    except (jwt.PyJWTError, KeyError):
        return
    session = db.scalar(select(RefreshSession).where(RefreshSession.jti_hash == jti_hash))
    if session and not session.revoked_at:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()
