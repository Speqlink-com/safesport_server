"""Create institutions and sports.

Revision ID: 20260926_0002
Revises: 20260926_0001
Create Date: 2026-09-26
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260926_0002"
down_revision: str | None = "20260926_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sports_name", "sports", ["name"], unique=True)
    op.create_table(
        "institutions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=False),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column("logo_path", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "city", "country", name="uq_institution_location"),
    )
    op.create_index("ix_institutions_is_active", "institutions", ["is_active"])
    op.create_index("ix_institutions_name", "institutions", ["name"])
    op.create_index("ix_institutions_type", "institutions", ["type"])
    op.create_table(
        "institution_sports",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("sport_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sport_id"], ["sports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("institution_id", "sport_id"),
    )


def downgrade() -> None:
    op.drop_table("institution_sports")
    op.drop_table("institutions")
    op.drop_table("sports")

