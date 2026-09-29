import secrets
import string

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import User

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _candidate() -> str:
    return "SAFE-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


def generate_safesport_id(db: Session) -> str:
    for _ in range(50):
        value = _candidate()
        if not db.scalar(select(User.id).where(User.safesport_id == value)):
            return value
    raise RuntimeError("Unable to generate a unique SafeSport ID")
