import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.auth import utcnow


class MovementSession(Base):
    __tablename__ = "movement_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    scheduled_at: Mapped[str] = mapped_column(String(60), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    drill: Mapped[str] = mapped_column(String(60), default="JUMP_LANDING")
    camera_view: Mapped[str] = mapped_column(String(60), default="FRONTAL")
    instructions_html: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="scheduled", index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    institution = relationship("Institution")
    created_by = relationship("User", foreign_keys=[created_by_user_id])


class MovementScreening(Base):
    __tablename__ = "movement_screenings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("movement_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    athlete_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True, index=True)
    athlete_safesport_id: Mapped[str] = mapped_column(String(20), index=True)
    athlete_name: Mapped[str] = mapped_column(String(200))
    sport: Mapped[str] = mapped_column(String(100), default="")
    team: Mapped[str] = mapped_column(String(100), default="")
    drill: Mapped[str] = mapped_column(String(60), default="JUMP_LANDING", index=True)
    camera_view: Mapped[str] = mapped_column(String(60), default="FRONTAL")
    status: Mapped[str] = mapped_column(String(60), default="VIDEO_PENDING", index=True)
    video_url: Mapped[str] = mapped_column(String(900), default="")
    video_public_id: Mapped[str] = mapped_column(String(500), default="", index=True)
    video_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ai_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    clinician_review: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    physio_review: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    report_summary: Mapped[str] = mapped_column(Text, default="")
    report_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    athlete = relationship("User", foreign_keys=[athlete_user_id])
    institution = relationship("Institution")
    session = relationship("MovementSession")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
