import hmac
import secrets
from fastapi import Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.auth import User
from app.services.auth_service import CSRF_COOKIE, get_access_user

settings = get_settings()


def set_csrf_cookie(response: Response) -> str:
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=24 * 60 * 60,
        httponly=False,
        secure=settings.secure_cookies,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path="/",
    )
    return token


def verify_csrf(
    request: Request,
    x_csrf_token: str | None = Header(default=None),
) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE)
    if not cookie_token or not x_csrf_token or not hmac.compare_digest(cookie_token, x_csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF validation failed")
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in {value.rstrip("/") for value in settings.cors_origin_list}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Request origin is not allowed")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    return get_access_user(request, db)


def require_system_admin(user: User = Depends(current_user)) -> User:
    if user.role != "sys-admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "System administrator access is required")
    return user
