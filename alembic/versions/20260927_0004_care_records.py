"""Create care records.

Revision ID: 20260927_0004
Revises: 20260927_0003
Create Date: 2026-09-27
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260927_0004"
down_revision: str | None = "20260927_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "care_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collection", sa.String(length=40), nullable=False),
        sa.Column("athlete_user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=60), nullable=False),
        sa.Column("date", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("assigned", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("coordination", sa.Text(), nullable=False),
        sa.Column("urgency", sa.String(length=40), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("encounter_id", sa.Uuid(), nullable=True),
        sa.Column("referral_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_encounter_id", sa.Uuid(), nullable=True),
        sa.Column("file_url", sa.String(length=800), nullable=False),
        sa.Column("file_name", sa.String(length=300), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["athlete_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["encounter_id"], ["ppe_assessments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_id"], ["care_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["referral_id"], ["care_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_encounter_id"], ["ppe_assessments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_care_records_athlete_user_id", "care_records", ["athlete_user_id"])
    op.create_index("ix_care_records_collection", "care_records", ["collection"])
    op.create_index("ix_care_records_encounter_id", "care_records", ["encounter_id"])
    op.create_index("ix_care_records_parent_id", "care_records", ["parent_id"])
    op.create_index("ix_care_records_referral_id", "care_records", ["referral_id"])
    op.create_index("ix_care_records_status", "care_records", ["status"])


def downgrade() -> None:
    op.drop_index("ix_care_records_status", table_name="care_records")
    op.drop_index("ix_care_records_referral_id", table_name="care_records")
    op.drop_index("ix_care_records_parent_id", table_name="care_records")
    op.drop_index("ix_care_records_encounter_id", table_name="care_records")
    op.drop_index("ix_care_records_collection", table_name="care_records")
    op.drop_index("ix_care_records_athlete_user_id", table_name="care_records")
    op.drop_table("care_records")
