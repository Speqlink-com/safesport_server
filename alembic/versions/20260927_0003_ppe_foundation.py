"""Create PPE workflow tables.

Revision ID: 20260927_0003
Revises: 20260926_0002
Create Date: 2026-09-27
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260927_0003"
down_revision: str | None = "20260926_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ppe_consents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("athlete_user_id", sa.Uuid(), nullable=False),
        sa.Column("clinical", sa.String(length=40), nullable=False),
        sa.Column("video", sa.Boolean(), nullable=False),
        sa.Column("research", sa.Boolean(), nullable=False),
        sa.Column("assent", sa.Boolean(), nullable=False),
        sa.Column("signer", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["athlete_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("athlete_user_id", name="uq_ppe_consent_athlete"),
    )
    op.create_index("ix_ppe_consents_athlete_user_id", "ppe_consents", ["athlete_user_id"])
    op.create_table(
        "ppe_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("athlete_user_id", sa.Uuid(), nullable=False),
        sa.Column("clinician_user_id", sa.Uuid(), nullable=True),
        sa.Column("physio_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("history_payload", sa.JSON(), nullable=False),
        sa.Column("clinical_payload", sa.JSON(), nullable=False),
        sa.Column("reviewed", sa.Boolean(), nullable=False),
        sa.Column("history_submitted", sa.Boolean(), nullable=False),
        sa.Column("physio_status", sa.String(length=40), nullable=False),
        sa.Column("physio_note", sa.Text(), nullable=False),
        sa.Column("finalized", sa.Boolean(), nullable=False),
        sa.Column("decision", sa.String(length=80), nullable=False),
        sa.Column("restrictions", sa.Text(), nullable=False),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("review_date", sa.Date(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("signature", sa.String(length=200), nullable=False),
        sa.Column("certificate_code", sa.String(length=80), nullable=True),
        sa.Column("certificate_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["athlete_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clinician_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["physio_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ppe_assessments_athlete_user_id", "ppe_assessments", ["athlete_user_id"])
    op.create_index("ix_ppe_assessments_clinician_user_id", "ppe_assessments", ["clinician_user_id"])
    op.create_index("ix_ppe_assessments_physio_user_id", "ppe_assessments", ["physio_user_id"])
    op.create_index("ix_ppe_assessments_status", "ppe_assessments", ["status"])
    op.create_index("ix_ppe_assessments_certificate_code", "ppe_assessments", ["certificate_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_ppe_assessments_certificate_code", table_name="ppe_assessments")
    op.drop_index("ix_ppe_assessments_status", table_name="ppe_assessments")
    op.drop_index("ix_ppe_assessments_physio_user_id", table_name="ppe_assessments")
    op.drop_index("ix_ppe_assessments_clinician_user_id", table_name="ppe_assessments")
    op.drop_index("ix_ppe_assessments_athlete_user_id", table_name="ppe_assessments")
    op.drop_table("ppe_assessments")
    op.drop_index("ix_ppe_consents_athlete_user_id", table_name="ppe_consents")
    op.drop_table("ppe_consents")
