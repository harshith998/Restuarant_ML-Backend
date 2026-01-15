from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import uuid

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant
    from app.models.waiter import Waiter
    from app.models.section import Section
    from app.models.visit import Visit
    from app.models.metrics import WaiterMetrics


class Shift(Base):
    """Work shifts for waiters."""

    __tablename__ = "shifts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )
    waiter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waiters.id"), nullable=False
    )
    section_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True
    )

    clock_in: Mapped[datetime] = mapped_column(nullable=False)
    clock_out: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, on_break, ended

    # Real-time aggregates
    tables_served: Mapped[int] = mapped_column(Integer, default=0)
    total_covers: Mapped[int] = mapped_column(Integer, default=0)
    total_tips: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    total_sales: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    restaurant: Mapped["Restaurant"] = relationship(
        "Restaurant", back_populates="shifts"
    )
    waiter: Mapped["Waiter"] = relationship(
        "Waiter", back_populates="shifts"
    )
    section: Mapped[Optional["Section"]] = relationship(
        "Section", back_populates="shifts"
    )
    visits: Mapped[List["Visit"]] = relationship(
        "Visit", back_populates="shift"
    )
    metrics: Mapped[List["WaiterMetrics"]] = relationship(
        "WaiterMetrics", back_populates="shift"
    )

    def __repr__(self) -> str:
        return f"<Shift(id={self.id}, waiter_id={self.waiter_id}, status={self.status})>"
