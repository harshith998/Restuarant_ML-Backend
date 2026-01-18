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
    from app.models.insights import WaiterInsights
    from app.models.scheduling import StaffAvailability, StaffPreference, ScheduleItem


class Waiter(Base):
    """Staff members (servers, hosts, bussers, runners, bartenders)."""

    __tablename__ = "waiters"

    # Roles that require individual performance tracking (tips, covers, tier scoring)
    PERFORMANCE_TRACKED_ROLES = {"server", "bartender"}
    # Roles scheduled primarily by availability (team-based, no individual metrics)
    AVAILABILITY_ONLY_ROLES = {"host", "busser", "runner", "chef"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Staff role - determines scheduling strategy and analytics applicability
    role: Mapped[str] = mapped_column(
        String(20), default="server"
    )  # server, host, busser, runner, bartender, chef

    # Performance tier (auto-calculated, only applies to PERFORMANCE_TRACKED_ROLES)
    tier: Mapped[str] = mapped_column(String(20), default="standard")  # strong, standard, developing
    composite_score: Mapped[float] = mapped_column(Numeric(5, 2), default=50.0)
    tier_updated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Lifetime stats (for historical context)
    total_shifts: Mapped[int] = mapped_column(Integer, default=0)
    total_covers: Mapped[int] = mapped_column(Integer, default=0)
    total_tips: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    total_tables_served: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_sales: Mapped[float] = mapped_column(Numeric(12, 2), default=0, server_default="0")

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
    insights: Mapped[List["WaiterInsights"]] = relationship(
        "WaiterInsights", back_populates="waiter", cascade="all, delete-orphan"
    )
    # Scheduling relationships
    availability: Mapped[List["StaffAvailability"]] = relationship(
        "StaffAvailability", back_populates="waiter", cascade="all, delete-orphan"
    )
    preferences: Mapped[Optional["StaffPreference"]] = relationship(
        "StaffPreference", back_populates="waiter", uselist=False, cascade="all, delete-orphan"
    )
    schedule_items: Mapped[List["ScheduleItem"]] = relationship(
        "ScheduleItem", back_populates="waiter", cascade="all, delete-orphan"
    )

    @property
    def requires_performance_tracking(self) -> bool:
        """Returns True if this staff role needs individual performance analytics."""
        return self.role in self.PERFORMANCE_TRACKED_ROLES

    @property
    def is_availability_only(self) -> bool:
        """Returns True if this staff role is scheduled by availability only (no performance optimization)."""
        return self.role in self.AVAILABILITY_ONLY_ROLES

    def __repr__(self) -> str:
        return f"<Waiter(id={self.id}, name={self.name}, role={self.role}, tier={self.tier})>"
