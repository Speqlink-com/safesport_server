"""Add movement screening module.

Revision ID: 20260929_0007
Revises: 20260928_0006
Create Date: 2026-09-29
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "20260929_0007"
down_revision: str | None = "20260928_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "movement_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("institution_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("scheduled_at", sa.String(length=60), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("drill", sa.String(length=60), nullable=False),
        sa.Column("camera_view", sa.String(length=60), nullable=False),
        sa.Column("instructions_html", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_movement_sessions_institution_id"), "movement_sessions", ["institution_id"])
    op.create_index(op.f("ix_movement_sessions_status"), "movement_sessions", ["status"])
    op.create_table(
        "movement_screenings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("athlete_user_id", sa.UUID(), nullable=False),
        sa.Column("institution_id", sa.UUID(), nullable=True),
        sa.Column("athlete_safesport_id", sa.String(length=20), nullable=False),
        sa.Column("athlete_name", sa.String(length=200), nullable=False),
        sa.Column("sport", sa.String(length=100), nullable=False),
        sa.Column("team", sa.String(length=100), nullable=False),
        sa.Column("drill", sa.String(length=60), nullable=False),
        sa.Column("camera_view", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=60), nullable=False),
        sa.Column("video_url", sa.String(length=900), nullable=False),
        sa.Column("video_public_id", sa.String(length=500), nullable=False),
        sa.Column("video_metadata", sa.JSON(), nullable=False),
        sa.Column("ai_result", sa.JSON(), nullable=False),
        sa.Column("clinician_review", sa.JSON(), nullable=False),
        sa.Column("physio_review", sa.JSON(), nullable=False),
        sa.Column("report_summary", sa.Text(), nullable=False),
        sa.Column("report_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["athlete_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["movement_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_movement_screenings_athlete_safesport_id"), "movement_screenings", ["athlete_safesport_id"])
    op.create_index(op.f("ix_movement_screenings_athlete_user_id"), "movement_screenings", ["athlete_user_id"])
    op.create_index(op.f("ix_movement_screenings_drill"), "movement_screenings", ["drill"])
    op.create_index(op.f("ix_movement_screenings_institution_id"), "movement_screenings", ["institution_id"])
    op.create_index(op.f("ix_movement_screenings_session_id"), "movement_screenings", ["session_id"])
    op.create_index(op.f("ix_movement_screenings_status"), "movement_screenings", ["status"])
    op.create_index(op.f("ix_movement_screenings_video_public_id"), "movement_screenings", ["video_public_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_movement_screenings_video_public_id"), table_name="movement_screenings")
    op.drop_index(op.f("ix_movement_screenings_status"), table_name="movement_screenings")
    op.drop_index(op.f("ix_movement_screenings_session_id"), table_name="movement_screenings")
    op.drop_index(op.f("ix_movement_screenings_institution_id"), table_name="movement_screenings")
    op.drop_index(op.f("ix_movement_screenings_drill"), table_name="movement_screenings")
    op.drop_index(op.f("ix_movement_screenings_athlete_user_id"), table_name="movement_screenings")
    op.drop_index(op.f("ix_movement_screenings_athlete_safesport_id"), table_name="movement_screenings")
    op.drop_table("movement_screenings")
    op.drop_index(op.f("ix_movement_sessions_status"), table_name="movement_sessions")
    op.drop_index(op.f("ix_movement_sessions_institution_id"), table_name="movement_sessions")
    op.drop_table("movement_sessions")
