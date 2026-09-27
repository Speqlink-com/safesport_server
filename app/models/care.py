import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.auth import utcnow


class CareRecord(Base):
    __tablename__ = "care_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    collection: Mapped[str] = mapped_column(String(40), index=True)
    athlete_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(60), index=True)
    date: Mapped[str] = mapped_column(String(40), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    assigned: Mapped[str] = mapped_column(String(200), default="")
    kind: Mapped[str] = mapped_column(String(80), default="")
    outcome: Mapped[str] = mapped_column(Text, default="")
    coordination: Mapped[str] = mapped_column(Text, default="")
    urgency: Mapped[str] = mapped_column(String(40), default="")
    progress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("care_records.id", ondelete="SET NULL"), nullable=True, index=True)
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ppe_assessments.id", ondelete="SET NULL"), nullable=True, index=True)
    referral_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("care_records.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewed_encounter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ppe_assessments.id", ondelete="SET NULL"), nullable=True)
    file_url: Mapped[str] = mapped_column(String(800), default="")
    file_name: Mapped[str] = mapped_column(String(300), default="")
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    athlete = relationship("User", foreign_keys=[athlete_user_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
