"""Create or update a development user for roles without self-registration."""
import argparse

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.auth import User
from app.services.security import hash_password
from app.services.safesport_id import generate_safesport_id

ROLES = ("athlete", "guardian", "clinician", "physiotherapist", "coach", "institution", "operations", "sys-admin")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--first-name", required=True)
    parser.add_argument("--last-name", required=True)
    parser.add_argument("--role", required=True, choices=ROLES)
    args = parser.parse_args()
    if len(args.password) < 8:
        parser.error("password must contain at least 8 characters")

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email.lower()))
        if user is None:
            user = User(
                email=args.email.lower(),
                safesport_id=generate_safesport_id(db),
                password_hash=hash_password(args.password),
                first_name=args.first_name,
                last_name=args.last_name,
                role=args.role,
            )
            db.add(user)
        else:
            user.password_hash = hash_password(args.password)
            user.first_name = args.first_name
            user.last_name = args.last_name
            user.role = args.role
            user.is_active = True
        db.commit()
        print(f"User ready: {user.email} ({user.role})")


if __name__ == "__main__":
    main()

