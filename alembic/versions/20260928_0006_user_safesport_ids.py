"""Add unique SafeSport IDs to users.

Revision ID: 20260928_0006
Revises: 20260927_0005
Create Date: 2026-09-28
"""
from collections.abc import Sequence
import secrets
import string

import sqlalchemy as sa
from alembic import op

revision: str = "20260928_0006"
down_revision: str | None = "20260927_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _candidate() -> str:
    return "SAFE-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


def _unique_id(connection) -> str:
    for _ in range(100):
        value = _candidate()
        exists = connection.execute(sa.text("select 1 from users where safesport_id = :value"), {"value": value}).first()
        if not exists:
            return value
    raise RuntimeError("Unable to generate a unique SafeSport ID")


def upgrade() -> None:
    op.add_column("users", sa.Column("safesport_id", sa.String(length=20), nullable=True))
    connection = op.get_bind()
    user_ids = connection.execute(sa.text("select id from users where safesport_id is null")).fetchall()
    for row in user_ids:
        connection.execute(
            sa.text("update users set safesport_id = :safesport_id where id = :id"),
            {"safesport_id": _unique_id(connection), "id": row.id},
        )
    op.alter_column("users", "safesport_id", existing_type=sa.String(length=20), nullable=False)
    op.create_index(op.f("ix_users_safesport_id"), "users", ["safesport_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_safesport_id"), table_name="users")
    op.drop_column("users", "safesport_id")
