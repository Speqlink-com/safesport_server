"""Create reports and messaging tables.

Revision ID: 20260927_0005
Revises: 20260927_0004
Create Date: 2026-09-27
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "20260927_0005"
down_revision: str | None = "20260927_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "term_reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("institution_id", sa.UUID(), nullable=True),
        sa.Column("athlete_user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["athlete_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_term_reports_athlete_user_id"), "term_reports", ["athlete_user_id"])
    op.create_index(op.f("ix_term_reports_institution_id"), "term_reports", ["institution_id"])
    op.create_index(op.f("ix_term_reports_status"), "term_reports", ["status"])
    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("institution_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_conversations_institution_id"), "conversations", ["institution_id"])
    op.create_index(op.f("ix_conversations_kind"), "conversations", ["kind"])
    op.create_table(
        "conversation_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "user_id", name="uq_conversation_member"),
    )
    op.create_index(op.f("ix_conversation_members_conversation_id"), "conversation_members", ["conversation_id"])
    op.create_index(op.f("ix_conversation_members_user_id"), "conversation_members", ["user_id"])
    op.create_table(
        "messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("sender_user_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("attachment_url", sa.String(length=800), nullable=False),
        sa.Column("attachment_name", sa.String(length=300), nullable=False),
        sa.Column("attachment_type", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_messages_conversation_id"), "messages", ["conversation_id"])
    op.create_index(op.f("ix_messages_created_at"), "messages", ["created_at"])
    op.create_index(op.f("ix_messages_sender_user_id"), "messages", ["sender_user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_messages_sender_user_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_created_at"), table_name="messages")
    op.drop_index(op.f("ix_messages_conversation_id"), table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_conversation_members_user_id"), table_name="conversation_members")
    op.drop_index(op.f("ix_conversation_members_conversation_id"), table_name="conversation_members")
    op.drop_table("conversation_members")
    op.drop_index(op.f("ix_conversations_kind"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_institution_id"), table_name="conversations")
    op.drop_table("conversations")
    op.drop_index(op.f("ix_term_reports_status"), table_name="term_reports")
    op.drop_index(op.f("ix_term_reports_institution_id"), table_name="term_reports")
    op.drop_index(op.f("ix_term_reports_athlete_user_id"), table_name="term_reports")
    op.drop_table("term_reports")
