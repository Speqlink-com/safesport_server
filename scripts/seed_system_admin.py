"""Seed the first System Administrator and the base sport catalogue."""
import argparse
import getpass
import os

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.auth import User
from app.models.institution import Sport
from app.services.security import hash_password
from app.services.safesport_id import generate_safesport_id

DEFAULT_SPORTS = ("Athletics", "Basketball", "Football", "Netball", "Rugby")


def _prompt_text(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or (default or "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default=os.getenv("SYSTEM_ADMIN_EMAIL"))
    parser.add_argument("--first-name", default=os.getenv("SYSTEM_ADMIN_FIRST_NAME"))
    parser.add_argument("--last-name", default=os.getenv("SYSTEM_ADMIN_LAST_NAME"))
    parser.add_argument("--password", default=os.getenv("SYSTEM_ADMIN_PASSWORD"))
    parser.add_argument("--no-prompt", action="store_true", help="Fail instead of asking for missing values.")
    args = parser.parse_args()

    if not args.email:
        if args.no_prompt:
            parser.error("provide --email or SYSTEM_ADMIN_EMAIL")
        args.email = _prompt_text("System Admin email")
    if not args.first_name:
        if args.no_prompt:
            parser.error("provide --first-name or SYSTEM_ADMIN_FIRST_NAME")
        args.first_name = _prompt_text("First name", "System")
    if not args.last_name:
        if args.no_prompt:
            parser.error("provide --last-name or SYSTEM_ADMIN_LAST_NAME")
        args.last_name = _prompt_text("Last name", "Administrator")

    password = args.password
    if not password:
        if args.no_prompt:
            parser.error("provide --password or SYSTEM_ADMIN_PASSWORD")
        password = getpass.getpass("System Admin password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            parser.error("passwords do not match")
    if len(password) < 8:
        parser.error("password must contain at least 8 characters")

    with SessionLocal() as db:
        email = args.email.strip().lower()
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                safesport_id=generate_safesport_id(db),
                password_hash=hash_password(password),
                first_name=args.first_name.strip(),
                last_name=args.last_name.strip(),
                role="sys-admin",
            )
            db.add(user)
        else:
            user.password_hash = hash_password(password)
            user.first_name = args.first_name.strip()
            user.last_name = args.last_name.strip()
            user.role = "sys-admin"
            user.is_active = True
            user.is_verified = True
        for name in DEFAULT_SPORTS:
            if not db.scalar(select(Sport.id).where(func.lower(Sport.name) == name.lower())):
                db.add(Sport(name=name))
        db.commit()
        print(f"System Administrator ready: {email}")
        print(f"Sport catalogue ready: {', '.join(DEFAULT_SPORTS)}")


if __name__ == "__main__":
    main()
