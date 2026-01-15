"""Tests for ShiftService."""
from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.shift_service import ShiftService


@pytest_asyncio.fixture
async def shift_service(db_session: AsyncSession) -> ShiftService:
    """Create a ShiftService instance."""
    return ShiftService(db_session)


class TestClockIn:
    """Tests for clock_in method."""

    async def test_creates_new_shift(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
    ):
        """Creates a new shift when clocking in."""
        # Use a waiter without an existing shift (create a new one)
        from app.models.waiter import Waiter
        new_waiter = Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="NewWaiter",
            tier="standard",
            composite_score=50.0,
        )
        db_session.add(new_waiter)
        await db_session.commit()

        shift = await shift_service.clock_in(
            restaurant_id=sample_restaurant.id,
            waiter_id=new_waiter.id,
            section_id=sample_sections[0].id,
        )

        assert shift is not None
        assert shift.waiter_id == new_waiter.id
        assert shift.restaurant_id == sample_restaurant.id
        assert shift.section_id == sample_sections[0].id
        assert shift.status == "active"
        assert shift.tables_served == 0
        assert shift.total_tips == 0

    async def test_raises_if_already_clocked_in(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Raises ValueError if waiter already has active shift."""
        alice = sample_waiters[0]  # Already has active shift

        with pytest.raises(ValueError, match="already has an active shift"):
            await shift_service.clock_in(
                restaurant_id=sample_restaurant.id,
                waiter_id=alice.id,
            )

    async def test_raises_for_invalid_waiter(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
    ):
        """Raises ValueError for non-existent waiter."""
        with pytest.raises(ValueError, match="not found"):
            await shift_service.clock_in(
                restaurant_id=sample_restaurant.id,
                waiter_id=uuid4(),
            )

    async def test_increments_waiter_total_shifts(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
    ):
        """Increments waiter's total_shifts counter."""
        from app.models.waiter import Waiter
        new_waiter = Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="NewWaiter2",
            tier="standard",
            composite_score=50.0,
            total_shifts=10,
        )
        db_session.add(new_waiter)
        await db_session.commit()

        original_shifts = new_waiter.total_shifts

        await shift_service.clock_in(
            restaurant_id=sample_restaurant.id,
            waiter_id=new_waiter.id,
        )

        await db_session.refresh(new_waiter)
        assert new_waiter.total_shifts == original_shifts + 1


class TestClockOut:
    """Tests for clock_out method."""

    async def test_ends_shift(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Sets clock_out time and status to ended."""
        alice_shift = sample_shifts[0]

        ended_shift = await shift_service.clock_out(alice_shift.id)

        assert ended_shift.status == "ended"
        assert ended_shift.clock_out is not None

    async def test_raises_for_already_ended_shift(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Raises ValueError if shift already ended."""
        alice_shift = sample_shifts[0]

        # End the shift first
        await shift_service.clock_out(alice_shift.id)

        # Try to end again
        with pytest.raises(ValueError, match="already ended"):
            await shift_service.clock_out(alice_shift.id)

    async def test_raises_for_invalid_shift(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
    ):
        """Raises ValueError for non-existent shift."""
        with pytest.raises(ValueError, match="not found"):
            await shift_service.clock_out(uuid4())


class TestStartBreak:
    """Tests for start_break method."""

    async def test_sets_status_to_on_break(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Sets shift status to on_break."""
        alice_shift = sample_shifts[0]  # Currently active

        updated = await shift_service.start_break(alice_shift.id)

        assert updated.status == "on_break"

    async def test_raises_if_already_on_break(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Raises ValueError if already on break."""
        dave_shift = sample_shifts[3]  # Already on break

        with pytest.raises(ValueError, match="already on break"):
            await shift_service.start_break(dave_shift.id)

    async def test_raises_if_shift_ended(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Raises ValueError if shift already ended."""
        alice_shift = sample_shifts[0]
        await shift_service.clock_out(alice_shift.id)

        with pytest.raises(ValueError, match="ended shift"):
            await shift_service.start_break(alice_shift.id)


class TestEndBreak:
    """Tests for end_break method."""

    async def test_sets_status_to_active(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Sets shift status back to active."""
        dave_shift = sample_shifts[3]  # Currently on break

        updated = await shift_service.end_break(dave_shift.id)

        assert updated.status == "active"

    async def test_raises_if_not_on_break(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Raises ValueError if not currently on break."""
        alice_shift = sample_shifts[0]  # Currently active

        with pytest.raises(ValueError, match="not on break"):
            await shift_service.end_break(alice_shift.id)


class TestGetActiveShift:
    """Tests for get_active_shift method."""

    async def test_returns_active_shift(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Returns the waiter's active shift."""
        alice = sample_waiters[0]

        shift = await shift_service.get_active_shift(alice.id)

        assert shift is not None
        assert shift.waiter_id == alice.id
        assert shift.status == "active"

    async def test_returns_on_break_shift(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Returns shift even if on_break (still considered active)."""
        dave = sample_waiters[3]

        shift = await shift_service.get_active_shift(dave.id)

        assert shift is not None
        assert shift.status == "on_break"

    async def test_returns_none_for_no_shift(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_waiters,
    ):
        """Returns None if waiter has no active shift."""
        from app.models.waiter import Waiter
        new_waiter = Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="NoShiftWaiter",
            tier="standard",
            composite_score=50.0,
        )
        db_session.add(new_waiter)
        await db_session.commit()

        shift = await shift_service.get_active_shift(new_waiter.id)

        assert shift is None


class TestUpdateShiftStats:
    """Tests for update_shift_stats method."""

    async def test_increments_tables_served(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Increments tables_served counter."""
        alice_shift = sample_shifts[0]
        original = alice_shift.tables_served

        updated = await shift_service.update_shift_stats(
            alice_shift.id,
            tables_served_delta=1,
        )

        assert updated.tables_served == original + 1

    async def test_increments_covers(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Increments total_covers counter."""
        alice_shift = sample_shifts[0]
        original = alice_shift.total_covers

        updated = await shift_service.update_shift_stats(
            alice_shift.id,
            covers_delta=4,
        )

        assert updated.total_covers == original + 4

    async def test_increments_tips_and_sales(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Increments tips and sales."""
        alice_shift = sample_shifts[0]
        original_tips = float(alice_shift.total_tips)
        original_sales = float(alice_shift.total_sales)

        updated = await shift_service.update_shift_stats(
            alice_shift.id,
            tips_delta=15.50,
            sales_delta=85.00,
        )

        assert float(updated.total_tips) == original_tips + 15.50
        assert float(updated.total_sales) == original_sales + 85.00


class TestAssignSection:
    """Tests for assign_section method."""

    async def test_assigns_section(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Assigns a section to the shift."""
        alice_shift = sample_shifts[0]
        patio = sample_sections[2]

        updated = await shift_service.assign_section(alice_shift.id, patio.id)

        assert updated.section_id == patio.id

    async def test_raises_for_ended_shift(
        self,
        db_session: AsyncSession,
        shift_service: ShiftService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Raises ValueError if shift already ended."""
        alice_shift = sample_shifts[0]
        await shift_service.clock_out(alice_shift.id)

        with pytest.raises(ValueError, match="ended shift"):
            await shift_service.assign_section(alice_shift.id, sample_sections[0].id)
