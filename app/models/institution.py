import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.auth import utcnow


institution_sports = Table(
    "institution_sports",
    Base.metadata,
    Column("institution_id", ForeignKey("institutions.id", ondelete="CASCADE"), primary_key=True),
    Column("sport_id", ForeignKey("sports.id", ondelete="CASCADE"), primary_key=True),
)


class Sport(Base):
    __tablename__ = "sports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    institutions: Mapped[list["Institution"]] = relationship(
        secondary=institution_sports, back_populates="sports"
    )


class Institution(Base):
    __tablename__ = "institutions"
    __table_args__ = (UniqueConstraint("name", "city", "country", name="uq_institution_location"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), index=True)
    type: Mapped[str] = mapped_column(String(40), index=True)
    city: Mapped[str] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(100))
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    sports: Mapped[list[Sport]] = relationship(
        secondary=institution_sports, back_populates="institutions", lazy="selectin"
    )

