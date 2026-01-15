from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant
    from app.models.section import Section
    from app.models.visit import Visit
    from app.models.metrics import TableStateLog


class Table(Base):
    """Physical tables in the restaurant."""

    __tablename__ = "tables"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "table_number", name="uq_restaurant_table_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )
    section_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True
    )
    table_number: Mapped[str] = mapped_column(String(20), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    table_type: Mapped[str] = mapped_column(String(20), nullable=False)  # booth, bar, table
    location: Mapped[str] = mapped_column(String(20), default="inside")  # inside, outside, patio, bar_area

    # Current state (updated by ML)
    state: Mapped[str] = mapped_column(String(20), default="clean")  # clean, occupied, dirty, reserved, unavailable
    state_confidence: Mapped[Optional[float]] = mapped_column(Numeric(3, 2), nullable=True)
    state_updated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Current visit (denormalized for fast access)
    current_visit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    restaurant: Mapped["Restaurant"] = relationship(
        "Restaurant", back_populates="tables"
    )
    section: Mapped[Optional["Section"]] = relationship(
        "Section", back_populates="tables"
    )
    visits: Mapped[List["Visit"]] = relationship(
        "Visit", back_populates="table", foreign_keys="Visit.table_id"
    )
    state_logs: Mapped[List["TableStateLog"]] = relationship(
        "TableStateLog", back_populates="table", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Table(id={self.id}, number={self.table_number}, state={self.state})>"
