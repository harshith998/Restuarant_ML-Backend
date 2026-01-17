from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Factory defaults for JSON columns (avoid mutable defaults)
def _empty_list() -> List[Any]:
    return []


def _empty_dict() -> Dict[str, Any]:
    return {}


# Use JSON that works with both SQLite (tests) and PostgreSQL (prod)
from sqlalchemy import JSON


if TYPE_CHECKING:
    from app.models.analytics import ScheduleInsights
    from app.models.restaurant import Restaurant
    from app.models.section import Section
    from app.models.waiter import Waiter


class StaffAvailability(Base):
    """Recurring weekly availability patterns for staff (like 7shifts).

    Each entry represents when a staff member is available/unavailable/preferred
    for a specific day of the week, with an optional effective date range.
    """

    __tablename__ = "staff_availability"
    __table_args__ = (
        # Prevent duplicate entries for same staff/day/time
        UniqueConstraint(
            "waiter_id", "day_of_week", "start_time", "end_time",
            name="uq_staff_availability_slot"
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

    # Day of week: 0=Monday, 1=Tuesday, ..., 6=Sunday
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    # available = can work, unavailable = cannot work, preferred = wants to work
    availability_type: Mapped[str] = mapped_column(
        String(20), default="available"
    )  # available, unavailable, preferred

    # Effective date range (when this pattern applies)
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    waiter: Mapped["Waiter"] = relationship("Waiter", back_populates="availability")
    restaurant: Mapped["Restaurant"] = relationship("Restaurant")

    def is_effective_on(self, check_date: date) -> bool:
        """Check if this availability pattern is effective on a given date."""
        if self.effective_from and check_date < self.effective_from:
            return False
        if self.effective_until and check_date > self.effective_until:
            return False
        return True

    def __repr__(self) -> str:
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        day_name = days[self.day_of_week] if 0 <= self.day_of_week <= 6 else "?"
        return f"<StaffAvailability({day_name} {self.start_time}-{self.end_time}, {self.availability_type})>"


class StaffPreference(Base):
    """Staff scheduling preferences - one record per staff member.

    Preferences are used for soft constraints in scheduling optimization.
    These don't apply to availability-only roles (hosts, bussers, runners).
    """

    __tablename__ = "staff_preferences"
    __table_args__ = (
        # One preference record per staff member
        UniqueConstraint("waiter_id", name="uq_staff_preferences_waiter"),
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

    # Preferred roles (for staff who can work multiple roles)
    preferred_roles: Mapped[Optional[List[Any]]] = mapped_column(
        JSON, default=_empty_list
    )  # ["server", "bartender"]

    # Preferred shift types
    preferred_shift_types: Mapped[Optional[List[Any]]] = mapped_column(
        JSON, default=_empty_list
    )  # ["morning", "evening", "closing"]

    # Preferred sections (by section_id)
    preferred_sections: Mapped[Optional[List[Any]]] = mapped_column(
        JSON, default=_empty_list
    )  # [uuid, uuid, ...]

    # Work limits
    max_shifts_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_hours_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_hours_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Avoid clopening (back-to-back closing and opening shifts)
    avoid_clopening: Mapped[bool] = mapped_column(Boolean, default=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    waiter: Mapped["Waiter"] = relationship("Waiter", back_populates="preferences")
    restaurant: Mapped["Restaurant"] = relationship("Restaurant")

    def __repr__(self) -> str:
        return f"<StaffPreference(waiter_id={self.waiter_id})>"


class Schedule(Base):
    """Weekly schedule container.

    Each schedule represents one week's worth of shift assignments.
    Schedules go through draft -> published -> archived lifecycle.
    """

    __tablename__ = "schedules"
    __table_args__ = (
        # One schedule per restaurant per week (by version)
        UniqueConstraint(
            "restaurant_id", "week_start_date", "version",
            name="uq_schedule_week_version"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )

    # Week identifier (Monday of the week)
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Lifecycle status
    status: Mapped[str] = mapped_column(
        String(20), default="draft"
    )  # draft, published, archived

    # How this schedule was created
    generated_by: Mapped[str] = mapped_column(
        String(20), default="manual"
    )  # manual, engine

    # Version for audit trail (increments on publish)
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Optional link to the engine run that generated this
    schedule_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedule_runs.id"), nullable=True
    )

    published_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    restaurant: Mapped["Restaurant"] = relationship("Restaurant")
    items: Mapped[List["ScheduleItem"]] = relationship(
        "ScheduleItem", back_populates="schedule", cascade="all, delete-orphan"
    )
    schedule_run: Mapped[Optional["ScheduleRun"]] = relationship(
        "ScheduleRun", back_populates="schedules"
    )
    insights: Mapped[Optional["ScheduleInsights"]] = relationship(
        "ScheduleInsights", back_populates="schedule", uselist=False
    )

    def __repr__(self) -> str:
        return f"<Schedule(week={self.week_start_date}, status={self.status}, v{self.version})>"


class ScheduleItem(Base):
    """Individual shift assignment within a schedule.

    Each item represents one staff member assigned to work a specific
    shift on a specific day.
    """

    __tablename__ = "schedule_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedules.id"), nullable=False
    )
    waiter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waiters.id"), nullable=False
    )

    # Role for this specific shift (may differ from staff's primary role)
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    # Optional section assignment
    section_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True
    )

    # Shift timing
    shift_date: Mapped[date] = mapped_column(Date, nullable=False)
    shift_start: Mapped[time] = mapped_column(Time, nullable=False)
    shift_end: Mapped[time] = mapped_column(Time, nullable=False)

    # How this item was created
    source: Mapped[str] = mapped_column(
        String(20), default="manual"
    )  # manual, suggestion, engine

    # Engine-computed scores (null for manual entries)
    preference_match_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    fairness_impact_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    schedule: Mapped["Schedule"] = relationship("Schedule", back_populates="items")
    waiter: Mapped["Waiter"] = relationship("Waiter", back_populates="schedule_items")
    section: Mapped[Optional["Section"]] = relationship("Section")
    reasoning: Mapped[Optional["ScheduleReasoning"]] = relationship(
        "ScheduleReasoning", back_populates="schedule_item", uselist=False
    )

    @property
    def duration_hours(self) -> float:
        """Calculate shift duration in hours."""
        start_dt = datetime.combine(self.shift_date, self.shift_start)
        end_dt = datetime.combine(self.shift_date, self.shift_end)
        # Handle overnight shifts
        if end_dt < start_dt:
            end_dt = datetime.combine(self.shift_date, self.shift_end) + timedelta(days=1)
        return (end_dt - start_dt).total_seconds() / 3600

    def __repr__(self) -> str:
        return f"<ScheduleItem({self.shift_date} {self.shift_start}-{self.shift_end}, role={self.role})>"


class ScheduleRun(Base):
    """Engine run metadata for schedule generation.

    Tracks the inputs, status, and summary of each scheduling engine run.
    """

    __tablename__ = "schedule_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )

    # Target week
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Engine version (for reproducibility)
    engine_version: Mapped[str] = mapped_column(String(20), default="1.0")

    # Run status
    run_status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, running, completed, failed

    # Frozen snapshot of inputs at run time
    inputs_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, default=_empty_dict
    )

    # Summary metrics from the run
    summary_metrics: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, default=_empty_dict
    )

    # Error message if run failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    restaurant: Mapped["Restaurant"] = relationship("Restaurant")
    schedules: Mapped[List["Schedule"]] = relationship(
        "Schedule", back_populates="schedule_run"
    )
    reasoning_entries: Mapped[List["ScheduleReasoning"]] = relationship(
        "ScheduleReasoning", back_populates="schedule_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ScheduleRun(week={self.week_start_date}, status={self.run_status})>"


class ScheduleReasoning(Base):
    """Per-item reasoning from the scheduling engine.

    Explains why each schedule item was assigned, including preference matches,
    constraint satisfaction, and fairness considerations.
    """

    __tablename__ = "schedule_reasoning"
    __table_args__ = (
        # One reasoning entry per schedule item
        UniqueConstraint("schedule_item_id", name="uq_schedule_reasoning_item"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    schedule_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedule_runs.id"), nullable=False
    )
    schedule_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedule_items.id"), nullable=False
    )

    # List of structured reasons for this assignment
    reasons: Mapped[Optional[List[Any]]] = mapped_column(
        JSON, default=_empty_list
    )  # ["Matched preference: Friday evening", "Within max hours", ...]

    # Any soft constraints that were violated
    constraint_violations: Mapped[Optional[List[Any]]] = mapped_column(
        JSON, default=_empty_list
    )  # ["Clopening warning: 10pm close, 6am open next day"]

    # Engine confidence in this assignment (0-100)
    confidence_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    schedule_run: Mapped["ScheduleRun"] = relationship(
        "ScheduleRun", back_populates="reasoning_entries"
    )
    schedule_item: Mapped["ScheduleItem"] = relationship(
        "ScheduleItem", back_populates="reasoning"
    )

    def __repr__(self) -> str:
        return f"<ScheduleReasoning(item_id={self.schedule_item_id}, confidence={self.confidence_score})>"


class StaffingRequirements(Base):
    """Minimum/maximum staffing requirements per time slot.

    Defines how many staff of each role are needed during specific time periods.
    Used by the scheduling engine to ensure adequate coverage.
    """

    __tablename__ = "staffing_requirements"
    __table_args__ = (
        # Prevent duplicate entries for same restaurant/day/time/role
        UniqueConstraint(
            "restaurant_id", "day_of_week", "start_time", "end_time", "role",
            name="uq_staffing_requirements_slot"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )

    # Day of week: 0=Monday, 1=Tuesday, ..., 6=Sunday
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    # Role this requirement applies to
    role: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # server, host, busser, runner, bartender

    # Staffing levels
    min_staff: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_staff: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Is this a high-demand "prime" shift (used for fairness calculations)
    is_prime_shift: Mapped[bool] = mapped_column(Boolean, default=False)

    # Effective date range (when this requirement applies)
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    restaurant: Mapped["Restaurant"] = relationship("Restaurant")

    def is_effective_on(self, check_date: date) -> bool:
        """Check if this requirement is effective on a given date."""
        if self.effective_from and check_date < self.effective_from:
            return False
        if self.effective_until and check_date > self.effective_until:
            return False
        return True

    def __repr__(self) -> str:
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        day_name = days[self.day_of_week] if 0 <= self.day_of_week <= 6 else "?"
        return f"<StaffingRequirements({day_name} {self.start_time}-{self.end_time}, {self.role}: {self.min_staff}-{self.max_staff or '∞'})>"
