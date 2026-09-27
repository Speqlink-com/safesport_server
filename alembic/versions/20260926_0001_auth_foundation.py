"""Create authentication tables.

Revision ID: 20260926_0001
Revises:
Create Date: 2026-09-26
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260926_0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("profile_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_table(
        "pending_registrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("profile_data", sa.JSON(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pending_registrations_email", "pending_registrations", ["email"])
    op.create_table(
        "otp_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_otp_challenges_email", "otp_challenges", ["email"])
    op.create_index("ix_otp_challenges_purpose", "otp_challenges", ["purpose"])
    op.create_index("ix_otp_challenges_subject_id", "otp_challenges", ["subject_id"])
    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("jti_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refresh_sessions_jti_hash", "refresh_sessions", ["jti_hash"], unique=True)
    op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_password_resets_token_hash", "password_resets", ["token_hash"], unique=True)
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])


def downgrade() -> None:
    op.drop_table("password_resets")
    op.drop_table("refresh_sessions")
    op.drop_table("otp_challenges")
    op.drop_table("pending_registrations")
    op.drop_table("users")

