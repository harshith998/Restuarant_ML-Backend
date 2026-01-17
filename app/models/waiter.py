from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant
    from app.models.shift import Shift
    from app.models.visit import Visit
    from app.models.metrics import WaiterMetrics


class Waiter(Base):
    """Staff members (waiters/servers)."""

    __tablename__ = "waiters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Performance tier (auto-calculated)
    tier: Mapped[str] = mapped_column(String(20), default="standard")  # strong, standard, developing
    composite_score: Mapped[float] = mapped_column(Numeric(5, 2), default=50.0)
    tier_updated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Lifetime stats (for historical context)
    total_shifts: Mapped[int] = mapped_column(Integer, default=0)
    total_covers: Mapped[int] = mapped_column(Integer, default=0)
    total_tips: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    restaurant: Mapped["Restaurant"] = relationship(
        "Restaurant", back_populates="waiters"
    )
    shifts: Mapped[List["Shift"]] = relationship(
        "Shift", back_populates="waiter", cascade="all, delete-orphan"
    )
    visits: Mapped[List["Visit"]] = relationship(
        "Visit", back_populates="waiter", foreign_keys="Visit.waiter_id"
    )
    transferred_visits: Mapped[List["Visit"]] = relationship(
        "Visit", foreign_keys="Visit.original_waiter_id"
    )
    metrics: Mapped[List["WaiterMetrics"]] = relationship(
        "WaiterMetrics", back_populates="waiter", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Waiter(id={self.id}, name={self.name}, tier={self.tier})>"
