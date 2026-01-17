"""Service for shift management operations."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shift import Shift
from app.models.waiter import Waiter


class ShiftService:
    """Service for shift management."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def clock_in(
        self,
        restaurant_id: UUID,
        waiter_id: UUID,
        section_id: Optional[UUID] = None,
    ) -> Shift:
        """
        Clock in a waiter. Creates a new shift record.

        Raises ValueError if waiter already has an active shift.
        """
        # Check waiter exists
        waiter = await self._get_waiter(waiter_id)
        if waiter is None:
            raise ValueError(f"Waiter {waiter_id} not found")

        # Check no active shift exists
        existing = await self.get_active_shift(waiter_id)
        if existing is not None:
            raise ValueError(f"Waiter {waiter_id} already has an active shift")

        # Create new shift
        shift = Shift(
            restaurant_id=restaurant_id,
            waiter_id=waiter_id,
            section_id=section_id,
            clock_in=datetime.utcnow(),
            status="active",
            tables_served=0,
            total_covers=0,
            total_tips=0,
            total_sales=0,
        )

        self.session.add(shift)

        # Update waiter's total shifts
        waiter.total_shifts += 1

        await self.session.commit()
        await self.session.refresh(shift)

        return shift

    async def clock_out(self, shift_id: UUID) -> Shift:
        """
        Clock out a waiter. Sets clock_out timestamp and status='ended'.
        """
        shift = await self._get_shift(shift_id)
        if shift is None:
            raise ValueError(f"Shift {shift_id} not found")

        if shift.status == "ended":
            raise ValueError(f"Shift {shift_id} already ended")

        shift.clock_out = datetime.utcnow()
        shift.status = "ended"

        await self.session.commit()
        await self.session.refresh(shift)

        return shift

    async def start_break(self, shift_id: UUID) -> Shift:
        """Set shift status to 'on_break'."""
        shift = await self._get_shift(shift_id)
        if shift is None:
            raise ValueError(f"Shift {shift_id} not found")

        if shift.status == "ended":
            raise ValueError(f"Cannot start break on ended shift")

        if shift.status == "on_break":
            raise ValueError(f"Waiter is already on break")

        shift.status = "on_break"

        await self.session.commit()
        await self.session.refresh(shift)

        return shift

    async def end_break(self, shift_id: UUID) -> Shift:
        """Set shift status back to 'active'."""
        shift = await self._get_shift(shift_id)
        if shift is None:
            raise ValueError(f"Shift {shift_id} not found")

        if shift.status != "on_break":
            raise ValueError(f"Waiter is not on break")

        shift.status = "active"

        await self.session.commit()
        await self.session.refresh(shift)

        return shift

    async def get_active_shift(self, waiter_id: UUID) -> Optional[Shift]:
        """Get waiter's current active or on_break shift."""
        stmt = (
            select(Shift)
            .where(Shift.waiter_id == waiter_id)
            .where(Shift.status.in_(["active", "on_break"]))
        )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_shift_by_id(self, shift_id: UUID) -> Optional[Shift]:
        """Get a shift by ID."""
        return await self._get_shift(shift_id)

    async def update_shift_stats(
        self,
        shift_id: UUID,
        tables_served_delta: int = 0,
        covers_delta: int = 0,
        tips_delta: float = 0,
        sales_delta: float = 0,
    ) -> Shift:
        """
        Update shift aggregates after seating or payment.

        Args:
            shift_id: The shift to update
            tables_served_delta: Increment for tables_served (usually 1)
            covers_delta: Increment for total_covers (party size)
            tips_delta: Increment for total_tips
            sales_delta: Increment for total_sales
        """
        shift = await self._get_shift(shift_id)
        if shift is None:
            raise ValueError(f"Shift {shift_id} not found")

        # Update shift aggregates
        shift.tables_served += tables_served_delta
        shift.total_covers += covers_delta
        shift.total_tips = float(shift.total_tips) + tips_delta
        shift.total_sales = float(shift.total_sales) + sales_delta

        # Update waiter's lifetime stats
        waiter = await self._get_waiter(shift.waiter_id)
        if waiter is not None:
            waiter.total_covers += covers_delta
            waiter.total_tips = float(waiter.total_tips) + tips_delta
            waiter.total_tables_served += tables_served_delta
            waiter.total_sales = float(waiter.total_sales) + sales_delta

        await self.session.commit()
        await self.session.refresh(shift)

        return shift

    async def assign_section(self, shift_id: UUID, section_id: UUID) -> Shift:
        """Assign or change a waiter's section for their shift."""
        shift = await self._get_shift(shift_id)
        if shift is None:
            raise ValueError(f"Shift {shift_id} not found")

        if shift.status == "ended":
            raise ValueError(f"Cannot assign section to ended shift")

        shift.section_id = section_id

        await self.session.commit()
        await self.session.refresh(shift)

        return shift

    async def _get_shift(self, shift_id: UUID) -> Optional[Shift]:
        """Get a shift by ID."""
        stmt = select(Shift).where(Shift.id == shift_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_waiter(self, waiter_id: UUID) -> Optional[Waiter]:
        """Get a waiter by ID."""
        stmt = select(Waiter).where(Waiter.id == waiter_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
