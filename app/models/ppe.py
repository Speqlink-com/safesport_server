import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.auth import utcnow


class PPEConsent(Base):
    __tablename__ = "ppe_consents"
    __table_args__ = (UniqueConstraint("athlete_user_id", name="uq_ppe_consent_athlete"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    athlete_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    clinical: Mapped[str] = mapped_column(String(40), default="deferred")
    video: Mapped[bool] = mapped_column(Boolean, default=False)
    research: Mapped[bool] = mapped_column(Boolean, default=False)
    assent: Mapped[bool] = mapped_column(Boolean, default=False)
    signer: Mapped[str] = mapped_column(String(200), default="")
    version: Mapped[str] = mapped_column(String(100), default="PPE privacy v1.0")
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    athlete: Mapped["User"] = relationship()


class PPEAssessment(Base):
    __tablename__ = "ppe_assessments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    athlete_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    clinician_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    physio_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    history_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    clinical_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    history_submitted: Mapped[bool] = mapped_column(Boolean, default=False)
    physio_status: Mapped[str] = mapped_column(String(40), default="not_required")
    physio_note: Mapped[str] = mapped_column(Text, default="")
    finalized: Mapped[bool] = mapped_column(Boolean, default=False)
    decision: Mapped[str] = mapped_column(String(80), default="pending_evaluation")
    restrictions: Mapped[str] = mapped_column(Text, default="")
    plan: Mapped[str] = mapped_column(Text, default="")
    review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    signature: Mapped[str] = mapped_column(String(200), default="")
    certificate_code: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True, index=True)
    certificate_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    athlete: Mapped["User"] = relationship(foreign_keys=[athlete_user_id])
    clinician: Mapped["User"] = relationship(foreign_keys=[clinician_user_id])
    physio: Mapped["User"] = relationship(foreign_keys=[physio_user_id])
