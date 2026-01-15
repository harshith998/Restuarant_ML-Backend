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
    from app.models.table import Table
    from app.models.waiter import Waiter
    from app.models.shift import Shift
    from app.models.waitlist import WaitlistEntry
    from app.models.menu import OrderItem


class Visit(Base):
    """Table visits (occupancy sessions)."""

    __tablename__ = "visits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tables.id"), nullable=False
    )
    waiter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waiters.id"), nullable=False
    )
    shift_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shifts.id"), nullable=False
    )
    waitlist_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waitlist.id"), nullable=True
    )

    # Party info
    party_size: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_covers: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # From ML person count

    # Timeline milestones
    seated_at: Mapped[datetime] = mapped_column(nullable=False)
    first_served_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    payment_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    cleared_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Computed metrics
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Payment summary (from POS)
    subtotal: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    tax: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    total: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    tip: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    tip_percentage: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    pos_transaction_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Transfer tracking
    original_waiter_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waiters.id"), nullable=True
    )
    transferred_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    restaurant: Mapped["Restaurant"] = relationship(
        "Restaurant", back_populates="visits"
    )
    table: Mapped["Table"] = relationship(
        "Table", back_populates="visits", foreign_keys=[table_id]
    )
    waiter: Mapped["Waiter"] = relationship(
        "Waiter", back_populates="visits", foreign_keys=[waiter_id]
    )
    shift: Mapped["Shift"] = relationship(
        "Shift", back_populates="visits"
    )
    waitlist_entry: Mapped[Optional["WaitlistEntry"]] = relationship(
        "WaitlistEntry", back_populates="visit"
    )
    order_items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem", back_populates="visit", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Visit(id={self.id}, table_id={self.table_id}, party_size={self.party_size})>"
