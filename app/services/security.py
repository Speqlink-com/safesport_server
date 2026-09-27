import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

settings = get_settings()
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def hash_secret(value: str) -> str:
    return hmac.new(settings.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()


def random_otp() -> str:
    return f"{secrets.randbelow(10_000):04d}"


def random_token() -> str:
    return secrets.token_urlsafe(32)


def create_jwt(subject: str, token_type: str, expires_delta: timedelta, jti: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if jti:
        payload["jti"] = jti
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_jwt(token: str, expected_type: str) -> dict[str, Any]:
    payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    if payload.get("type") != expected_type or not payload.get("sub"):
        raise jwt.InvalidTokenError("Unexpected token type")
    return payload


def new_jti() -> str:
    return str(uuid.uuid4())


def is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= datetime.now(timezone.utc)
