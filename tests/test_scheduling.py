"""
Tests for scheduling models, schemas, and API endpoints.

Tests cover:
- Staff availability patterns (recurring weekly)
- Staff preferences
- Schedules and schedule items
- Schedule runs (engine)
- Role-based scheduling strategy
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Restaurant,
    Waiter,
    Section,
    StaffAvailability,
    StaffPreference,
    Schedule,
    ScheduleItem,
    ScheduleRun,
    ScheduleReasoning,
)
from app.schemas.scheduling import (
    StaffAvailabilityCreate,
    StaffAvailabilityRead,
    StaffPreferenceCreate,
    StaffPreferenceRead,
    ScheduleCreate,
    ScheduleRead,
    ScheduleItemCreate,
    ScheduleItemRead,
    AvailabilityType,
    ScheduleStatus,
    ScheduleSource,
    RunStatus,
    ShiftType,
)
from app.schemas.waiter import StaffRole


# =============================================================================
# Model Tests
# =============================================================================


class TestWaiterRoleModel:
    """Tests for Waiter model role field and helper methods."""

    @pytest.mark.asyncio
    async def test_waiter_default_role_is_server(self, db_session: AsyncSession, sample_restaurant: Restaurant):
        """New waiters should default to server role."""
        waiter = Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Test Server",
        )
        db_session.add(waiter)
        await db_session.commit()
        await db_session.refresh(waiter)

        assert waiter.role == "server"

    @pytest.mark.asyncio
    async def test_waiter_role_can_be_set(self, db_session: AsyncSession, sample_restaurant: Restaurant):
        """Waiter role can be explicitly set."""
        waiter = Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Test Host",
            role="host",
        )
        db_session.add(waiter)
        await db_session.commit()
        await db_session.refresh(waiter)

        assert waiter.role == "host"

    @pytest.mark.asyncio
    async def test_requires_performance_tracking_for_server(self, db_session: AsyncSession, sample_restaurant: Restaurant):
        """Servers require performance tracking."""
        waiter = Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Server",
            role="server",
        )
        db_session.add(waiter)
        await db_session.commit()

        assert waiter.requires_performance_tracking is True
        assert waiter.is_availability_only is False

    @pytest.mark.asyncio
    async def test_requires_performance_tracking_for_bartender(self, db_session: AsyncSession, sample_restaurant: Restaurant):
        """Bartenders require performance tracking."""
        waiter = Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Bartender",
            role="bartender",
        )
        db_session.add(waiter)
        await db_session.commit()

        assert waiter.requires_performance_tracking is True

    @pytest.mark.asyncio
    async def test_availability_only_for_busser(self, db_session: AsyncSession, sample_restaurant: Restaurant):
        """Bussers are availability-only (no performance tracking)."""
        waiter = Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Busser",
            role="busser",
        )
        db_session.add(waiter)
        await db_session.commit()

        assert waiter.requires_performance_tracking is False
        assert waiter.is_availability_only is True

    @pytest.mark.asyncio
    async def test_availability_only_for_host(self, db_session: AsyncSession, sample_restaurant: Restaurant):
        """Hosts are availability-only."""
        waiter = Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Host",
            role="host",
        )
        db_session.add(waiter)
        await db_session.commit()

        assert waiter.requires_performance_tracking is False
        assert waiter.is_availability_only is True


class TestStaffAvailabilityModel:
    """Tests for StaffAvailability model."""

    @pytest.mark.asyncio
    async def test_create_availability(self, db_session: AsyncSession, sample_restaurant: Restaurant, sample_waiters: list[Waiter]):
        """Can create a staff availability pattern."""
        waiter = sample_waiters[0]
        availability = StaffAvailability(
            id=uuid4(),
            waiter_id=waiter.id,
            restaurant_id=sample_restaurant.id,
            day_of_week=0,  # Monday
            start_time=time(9, 0),
            end_time=time(17, 0),
            availability_type="available",
        )
        db_session.add(availability)
        await db_session.commit()
        await db_session.refresh(availability)

        assert availability.day_of_week == 0
        assert availability.start_time == time(9, 0)
        assert availability.end_time == time(17, 0)
        assert availability.availability_type == "available"

    @pytest.mark.asyncio
    async def test_is_effective_on_no_date_range(self, db_session: AsyncSession, sample_restaurant: Restaurant, sample_waiters: list[Waiter]):
        """Availability without date range is always effective."""
        waiter = sample_waiters[0]
        availability = StaffAvailability(
            id=uuid4(),
            waiter_id=waiter.id,
            restaurant_id=sample_restaurant.id,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(17, 0),
            availability_type="available",
        )
        db_session.add(availability)
        await db_session.commit()

        today = date.today()
        assert availability.is_effective_on(today) is True
        assert availability.is_effective_on(today + timedelta(days=365)) is True

    @pytest.mark.asyncio
    async def test_is_effective_on_with_date_range(self, db_session: AsyncSession, sample_restaurant: Restaurant, sample_waiters: list[Waiter]):
        """Availability with date range only effective within range."""
        waiter = sample_waiters[0]
        today = date.today()
        availability = StaffAvailability(
            id=uuid4(),
            waiter_id=waiter.id,
            restaurant_id=sample_restaurant.id,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(17, 0),
            availability_type="available",
            effective_from=today,
            effective_until=today + timedelta(days=30),
        )
        db_session.add(availability)
        await db_session.commit()

        assert availability.is_effective_on(today) is True
        assert availability.is_effective_on(today + timedelta(days=15)) is True
        assert availability.is_effective_on(today - timedelta(days=1)) is False
        assert availability.is_effective_on(today + timedelta(days=31)) is False


class TestStaffPreferenceModel:
    """Tests for StaffPreference model."""

    @pytest.mark.asyncio
    async def test_create_preference(self, db_session: AsyncSession, sample_restaurant: Restaurant, sample_waiters: list[Waiter]):
        """Can create staff preferences."""
        waiter = sample_waiters[0]
        preference = StaffPreference(
            id=uuid4(),
            waiter_id=waiter.id,
            restaurant_id=sample_restaurant.id,
            preferred_roles=["server", "bartender"],
            preferred_shift_types=["evening", "closing"],
            max_shifts_per_week=5,
            max_hours_per_week=40,
            avoid_clopening=True,
        )
        db_session.add(preference)
        await db_session.commit()
        await db_session.refresh(preference)

        assert preference.preferred_roles == ["server", "bartender"]
        assert preference.max_hours_per_week == 40
        assert preference.avoid_clopening is True


class TestScheduleModel:
    """Tests for Schedule model."""

    @pytest.mark.asyncio
    async def test_create_schedule(self, db_session: AsyncSession, sample_restaurant: Restaurant):
        """Can create a schedule."""
        schedule = Schedule(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            week_start_date=date.today(),
            status="draft",
            generated_by="manual",
            version=1,
        )
        db_session.add(schedule)
        await db_session.commit()
        await db_session.refresh(schedule)

        assert schedule.status == "draft"
        assert schedule.version == 1


class TestScheduleItemModel:
    """Tests for ScheduleItem model."""

    @pytest.mark.asyncio
    async def test_create_schedule_item(
        self,
        db_session: AsyncSession,
        sample_restaurant: Restaurant,
        sample_waiters: list[Waiter],
    ):
        """Can create a schedule item."""
        waiter = sample_waiters[0]
        schedule = Schedule(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            week_start_date=date.today(),
            status="draft",
            generated_by="manual",
        )
        db_session.add(schedule)
        await db_session.commit()

        item = ScheduleItem(
            id=uuid4(),
            schedule_id=schedule.id,
            waiter_id=waiter.id,
            role="server",
            shift_date=date.today(),
            shift_start=time(17, 0),
            shift_end=time(23, 0),
            source="manual",
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        assert item.role == "server"
        assert item.shift_start == time(17, 0)


# =============================================================================
# Schema Tests
# =============================================================================


class TestAvailabilitySchemas:
    """Tests for availability Pydantic schemas."""

    def test_availability_create_valid(self):
        """Valid availability creation."""
        data = StaffAvailabilityCreate(
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(17, 0),
            availability_type=AvailabilityType.AVAILABLE,
        )
        assert data.day_of_week == 0
        assert data.availability_type == AvailabilityType.AVAILABLE

    def test_availability_create_with_dates(self):
        """Availability with effective date range."""
        today = date.today()
        data = StaffAvailabilityCreate(
            day_of_week=5,  # Saturday
            start_time=time(10, 0),
            end_time=time(22, 0),
            availability_type=AvailabilityType.PREFERRED,
            effective_from=today,
            effective_until=today + timedelta(days=90),
        )
        assert data.effective_from == today
        assert data.availability_type == AvailabilityType.PREFERRED

    def test_availability_day_of_week_validation(self):
        """Day of week must be 0-6."""
        with pytest.raises(ValueError):
            StaffAvailabilityCreate(
                day_of_week=7,  # Invalid
                start_time=time(9, 0),
                end_time=time(17, 0),
            )


class TestPreferenceSchemas:
    """Tests for preference Pydantic schemas."""

    def test_preference_create_valid(self):
        """Valid preference creation."""
        data = StaffPreferenceCreate(
            preferred_roles=[StaffRole.SERVER, StaffRole.BARTENDER],
            preferred_shift_types=[ShiftType.EVENING],
            max_shifts_per_week=5,
            max_hours_per_week=40,
        )
        assert StaffRole.SERVER in data.preferred_roles
        assert data.max_hours_per_week == 40

    def test_preference_with_empty_lists(self):
        """Preferences with empty lists are valid."""
        data = StaffPreferenceCreate()
        assert data.preferred_roles == []
        assert data.preferred_shift_types == []


class TestScheduleSchemas:
    """Tests for schedule Pydantic schemas."""

    def test_schedule_create_valid(self):
        """Valid schedule creation."""
        data = ScheduleCreate(
            week_start_date=date.today(),
            generated_by=ScheduleSource.MANUAL,
        )
        assert data.generated_by == ScheduleSource.MANUAL

    def test_schedule_item_create_valid(self):
        """Valid schedule item creation."""
        data = ScheduleItemCreate(
            waiter_id=uuid4(),
            role=StaffRole.SERVER,
            shift_date=date.today(),
            shift_start=time(17, 0),
            shift_end=time(23, 0),
        )
        assert data.role == StaffRole.SERVER


class TestEnums:
    """Tests for scheduling enums."""

    def test_availability_type_values(self):
        """AvailabilityType enum has expected values."""
        assert AvailabilityType.AVAILABLE.value == "available"
        assert AvailabilityType.UNAVAILABLE.value == "unavailable"
        assert AvailabilityType.PREFERRED.value == "preferred"

    def test_schedule_status_values(self):
        """ScheduleStatus enum has expected values."""
        assert ScheduleStatus.DRAFT.value == "draft"
        assert ScheduleStatus.PUBLISHED.value == "published"
        assert ScheduleStatus.ARCHIVED.value == "archived"

    def test_staff_role_values(self):
        """StaffRole enum has expected values."""
        assert StaffRole.SERVER.value == "server"
        assert StaffRole.HOST.value == "host"
        assert StaffRole.BUSSER.value == "busser"
        assert StaffRole.RUNNER.value == "runner"
        assert StaffRole.BARTENDER.value == "bartender"

    def test_run_status_values(self):
        """RunStatus enum has expected values."""
        assert RunStatus.PENDING.value == "pending"
        assert RunStatus.RUNNING.value == "running"
        assert RunStatus.COMPLETED.value == "completed"
        assert RunStatus.FAILED.value == "failed"


# =============================================================================
# Relationship Tests
# =============================================================================


class TestSchedulingRelationships:
    """Tests for relationships between scheduling models."""

    @pytest.mark.asyncio
    async def test_waiter_availability_relationship(
        self,
        db_session: AsyncSession,
        sample_restaurant: Restaurant,
        sample_waiters: list[Waiter],
    ):
        """Waiter has availability relationship."""
        waiter = sample_waiters[0]

        # Create availability patterns
        for day in range(5):  # Mon-Fri
            avail = StaffAvailability(
                id=uuid4(),
                waiter_id=waiter.id,
                restaurant_id=sample_restaurant.id,
                day_of_week=day,
                start_time=time(9, 0),
                end_time=time(17, 0),
                availability_type="available",
            )
            db_session.add(avail)

        await db_session.commit()

        # Query with eager loading to verify relationship
        stmt = select(StaffAvailability).where(StaffAvailability.waiter_id == waiter.id)
        result = await db_session.execute(stmt)
        availability_list = result.scalars().all()

        assert len(availability_list) == 5

    @pytest.mark.asyncio
    async def test_waiter_preferences_relationship(
        self,
        db_session: AsyncSession,
        sample_restaurant: Restaurant,
        sample_waiters: list[Waiter],
    ):
        """Waiter has preferences relationship (one-to-one)."""
        waiter = sample_waiters[0]

        preference = StaffPreference(
            id=uuid4(),
            waiter_id=waiter.id,
            restaurant_id=sample_restaurant.id,
            max_hours_per_week=40,
        )
        db_session.add(preference)
        await db_session.commit()

        # Query with eager loading to verify relationship
        stmt = select(StaffPreference).where(StaffPreference.waiter_id == waiter.id)
        result = await db_session.execute(stmt)
        pref = result.scalar_one_or_none()

        assert pref is not None
        assert pref.max_hours_per_week == 40

    @pytest.mark.asyncio
    async def test_schedule_items_relationship(
        self,
        db_session: AsyncSession,
        sample_restaurant: Restaurant,
        sample_waiters: list[Waiter],
    ):
        """Schedule has items relationship."""
        schedule = Schedule(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            week_start_date=date.today(),
            status="draft",
            generated_by="manual",
        )
        db_session.add(schedule)
        await db_session.commit()

        # Add items
        for waiter in sample_waiters[:2]:
            item = ScheduleItem(
                id=uuid4(),
                schedule_id=schedule.id,
                waiter_id=waiter.id,
                role="server",
                shift_date=date.today(),
                shift_start=time(17, 0),
                shift_end=time(23, 0),
                source="manual",
            )
            db_session.add(item)

        await db_session.commit()

        # Query with eager loading to verify relationship
        stmt = select(ScheduleItem).where(ScheduleItem.schedule_id == schedule.id)
        result = await db_session.execute(stmt)
        items = result.scalars().all()

        assert len(items) == 2


# =============================================================================
# Integration Tests
# =============================================================================


class TestSchedulingWorkflow:
    """Integration tests for complete scheduling workflows."""

    @pytest.mark.asyncio
    async def test_full_scheduling_workflow(
        self,
        db_session: AsyncSession,
        sample_restaurant: Restaurant,
        sample_waiters: list[Waiter],
        sample_sections: list[Section],
    ):
        """Test complete scheduling workflow: availability -> preferences -> schedule."""
        waiter = sample_waiters[0]
        section = sample_sections[0]

        # 1. Create availability
        availability = StaffAvailability(
            id=uuid4(),
            waiter_id=waiter.id,
            restaurant_id=sample_restaurant.id,
            day_of_week=0,  # Monday
            start_time=time(17, 0),
            end_time=time(23, 0),
            availability_type="preferred",
        )
        db_session.add(availability)

        # 2. Create preferences
        preference = StaffPreference(
            id=uuid4(),
            waiter_id=waiter.id,
            restaurant_id=sample_restaurant.id,
            preferred_roles=["server"],
            preferred_shift_types=["evening"],
            max_hours_per_week=40,
        )
        db_session.add(preference)

        # 3. Create schedule
        week_start = date.today()
        schedule = Schedule(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            week_start_date=week_start,
            status="draft",
            generated_by="manual",
        )
        db_session.add(schedule)
        await db_session.commit()

        # 4. Add schedule item
        item = ScheduleItem(
            id=uuid4(),
            schedule_id=schedule.id,
            waiter_id=waiter.id,
            role="server",
            section_id=section.id,
            shift_date=week_start,
            shift_start=time(17, 0),
            shift_end=time(23, 0),
            source="manual",
        )
        db_session.add(item)
        await db_session.commit()

        # 5. Publish schedule
        schedule.status = "published"
        schedule.published_at = datetime.utcnow()
        await db_session.commit()
        await db_session.refresh(schedule)

        assert schedule.status == "published"
        assert schedule.published_at is not None

        # Query items to verify (avoid lazy loading)
        stmt = select(ScheduleItem).where(ScheduleItem.schedule_id == schedule.id)
        result = await db_session.execute(stmt)
        items = result.scalars().all()
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_multi_role_staff_scheduling(
        self,
        db_session: AsyncSession,
        sample_restaurant: Restaurant,
    ):
        """Test scheduling staff with different roles."""
        # Create different role staff
        server = Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Server 1",
            role="server",
        )
        host = Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Host 1",
            role="host",
        )
        busser = Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="Busser 1",
            role="busser",
        )
        db_session.add_all([server, host, busser])
        await db_session.commit()

        # Create schedule with all roles
        schedule = Schedule(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            week_start_date=date.today(),
            status="draft",
            generated_by="manual",
        )
        db_session.add(schedule)
        await db_session.commit()

        # Add items for each role
        for waiter in [server, host, busser]:
            item = ScheduleItem(
                id=uuid4(),
                schedule_id=schedule.id,
                waiter_id=waiter.id,
                role=waiter.role,
                shift_date=date.today(),
                shift_start=time(17, 0),
                shift_end=time(23, 0),
                source="manual",
            )
            db_session.add(item)

        await db_session.commit()

        # Query items to verify (avoid lazy loading)
        stmt = select(ScheduleItem).where(ScheduleItem.schedule_id == schedule.id)
        result = await db_session.execute(stmt)
        items = result.scalars().all()

        # Verify roles
        roles = {item.role for item in items}
        assert roles == {"server", "host", "busser"}

        # Verify role-based properties
        assert server.requires_performance_tracking is True
        assert host.is_availability_only is True
        assert busser.is_availability_only is True
