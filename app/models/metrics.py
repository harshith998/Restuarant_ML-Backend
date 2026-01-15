from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Dict, Optional
import uuid

from sqlalchemy import Date, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.waiter import Waiter
    from app.models.restaurant import Restaurant
    from app.models.shift import Shift
    from app.models.menu import MenuItem
    from app.models.table import Table


class WaiterMetrics(Base):
    """Waiter metrics (pre-computed rollups)."""

    __tablename__ = "waiter_metrics"
    __table_args__ = (
        UniqueConstraint(
            "waiter_id", "period_type", "period_start", "shift_id",
            name="uq_waiter_metrics_lookup"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    waiter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waiters.id"), nullable=False
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )

    period_type: Mapped[str] = mapped_column(String(20), nullable=False)  # shift, daily, weekly, monthly
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    shift_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shifts.id"), nullable=True
    )

    # Counts
    tables_served: Mapped[int] = mapped_column(Integer, default=0)
    total_covers: Mapped[int] = mapped_column(Integer, default=0)
    total_visits: Mapped[int] = mapped_column(Integer, default=0)

    # Money
    total_sales: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total_tips: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    avg_tip_percentage: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    avg_check_size: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    # Time
    avg_turn_time_minutes: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), nullable=True)
    min_turn_time_minutes: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), nullable=True)
    max_turn_time_minutes: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), nullable=True)

    computed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    waiter: Mapped["Waiter"] = relationship("Waiter", back_populates="metrics")
    restaurant: Mapped["Restaurant"] = relationship("Restaurant")
    shift: Mapped[Optional["Shift"]] = relationship("Shift", back_populates="metrics")

    def __repr__(self) -> str:
        return f"<WaiterMetrics(waiter_id={self.waiter_id}, period={self.period_type})>"


class RestaurantMetrics(Base):
    """Restaurant-level metrics."""

    __tablename__ = "restaurant_metrics"
    __table_args__ = (
        UniqueConstraint(
            "restaurant_id", "period_type", "period_start",
            name="uq_restaurant_metrics_lookup"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )

    period_type: Mapped[str] = mapped_column(String(20), nullable=False)  # hourly, daily, weekly, monthly
    period_start: Mapped[datetime] = mapped_column(nullable=False)
    period_end: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Volume
    total_parties: Mapped[int] = mapped_column(Integer, default=0)
    total_covers: Mapped[int] = mapped_column(Integer, default=0)
    peak_occupancy: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Revenue
    total_revenue: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total_tips: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    avg_check_size: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    # Timing
    avg_turn_time_minutes: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), nullable=True)
    avg_wait_time_minutes: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), nullable=True)

    # Staffing
    waiter_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    covers_per_waiter: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), nullable=True)

    computed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    restaurant: Mapped["Restaurant"] = relationship("Restaurant", back_populates="metrics")

    def __repr__(self) -> str:
        return f"<RestaurantMetrics(restaurant_id={self.restaurant_id}, period={self.period_type})>"


class MenuItemMetrics(Base):
    """Menu item analytics."""

    __tablename__ = "menu_item_metrics"
    __table_args__ = (
        UniqueConstraint(
            "menu_item_id", "period_type", "period_start",
            name="uq_menu_item_metrics_lookup"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menu_items.id"), nullable=False
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )

    period_type: Mapped[str] = mapped_column(String(20), nullable=False)  # daily, weekly, monthly
    period_start: Mapped[date] = mapped_column(Date, nullable=False)

    times_ordered: Mapped[int] = mapped_column(Integer, default=0)
    total_revenue: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    # Distribution (for pattern analysis)
    hourly_distribution: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    menu_item: Mapped["MenuItem"] = relationship("MenuItem", back_populates="metrics")
    restaurant: Mapped["Restaurant"] = relationship("Restaurant")

    def __repr__(self) -> str:
        return f"<MenuItemMetrics(menu_item_id={self.menu_item_id}, period={self.period_type})>"


class TableStateLog(Base):
    """Table state history (for ML accuracy tracking)."""

    __tablename__ = "table_state_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tables.id"), nullable=False
    )

    previous_state: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    new_state: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(3, 2), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # 'ml', 'host', 'system'

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    table: Mapped["Table"] = relationship("Table", back_populates="state_logs")

    def __repr__(self) -> str:
        return f"<TableStateLog(table_id={self.table_id}, {self.previous_state} -> {self.new_state})>"
