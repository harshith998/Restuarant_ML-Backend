"""
Tests for SQLAlchemy models.

These tests verify that models work correctly in real-world scenarios:
- Creating and querying restaurants with relationships
- Managing table states and visits
- Tracking waiter shifts and metrics
- Processing waitlist entries
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Restaurant,
    Section,
    Table,
    Waiter,
    Shift,
    WaitlistEntry,
    Visit,
    MenuItem,
    OrderItem,
)


class TestRestaurantModel:
    """Tests for Restaurant model and relationships."""

    @pytest.mark.asyncio
    async def test_create_restaurant(self, db_session: AsyncSession):
        """Test creating a new restaurant with config."""
        restaurant = Restaurant(
            name="Test Bistro",
            timezone="America/Chicago",
            config={"routing": {"mode": "rotation"}},
        )
        db_session.add(restaurant)
        await db_session.commit()

        assert restaurant.id is not None
        assert restaurant.name == "Test Bistro"
        assert restaurant.config["routing"]["mode"] == "rotation"

    @pytest.mark.asyncio
    async def test_restaurant_with_sections(
        self, db_session: AsyncSession, sample_restaurant: Restaurant, sample_sections: list[Section]
    ):
        """Test loading restaurant with its sections."""
        result = await db_session.execute(
            select(Restaurant)
            .options(selectinload(Restaurant.sections))
            .where(Restaurant.id == sample_restaurant.id)
        )
        restaurant = result.scalar_one()

        assert len(restaurant.sections) == 3
        section_names = {s.name for s in restaurant.sections}
        assert section_names == {"Bar", "Main Floor", "Patio"}


class TestTableModel:
    """Tests for Table model and state management."""

    @pytest.mark.asyncio
    async def test_table_states(self, db_session: AsyncSession, sample_tables: list[Table]):
        """Test that tables have correct initial states."""
        result = await db_session.execute(select(Table))
        tables = result.scalars().all()

        # Count tables by state
        states = {}
        for table in tables:
            states[table.state] = states.get(table.state, 0) + 1

        assert states["clean"] >= 8  # Most tables should be clean
        assert states["occupied"] == 2
        assert states["dirty"] == 1
        assert states["unavailable"] == 1

    @pytest.mark.asyncio
    async def test_update_table_state(self, db_session: AsyncSession, sample_tables: list[Table]):
        """Test updating table state (simulating ML update)."""
        table = sample_tables[0]  # B1 at bar

        table.state = "occupied"
        table.state_confidence = 0.95
        table.state_updated_at = datetime.utcnow()

        await db_session.commit()
        await db_session.refresh(table)

        assert table.state == "occupied"
        assert float(table.state_confidence) == 0.95

    @pytest.mark.asyncio
    async def test_find_available_tables_for_party(
        self, db_session: AsyncSession, sample_tables: list[Table]
    ):
        """
        Real-world scenario: Find tables for a party of 4.
        Should return clean tables with capacity >= 4.
        """
        result = await db_session.execute(
            select(Table)
            .where(Table.state == "clean")
            .where(Table.capacity >= 4)
        )
        available = result.scalars().all()

        # Should find: T1, T3, Booth1, Booth2, P1, P2
        assert len(available) >= 5
        for table in available:
            assert table.state == "clean"
            assert table.capacity >= 4


class TestWaiterModel:
    """Tests for Waiter model and performance tracking."""

    @pytest.mark.asyncio
    async def test_waiter_tiers(self, db_session: AsyncSession, sample_waiters: list[Waiter]):
        """Test that waiters have appropriate tier assignments."""
        tiers = {w.name: w.tier for w in sample_waiters}

        assert tiers["Alice"] == "strong"
        assert tiers["Bob"] == "standard"
        assert tiers["Carol"] == "developing"

    @pytest.mark.asyncio
    async def test_waiter_composite_score_ordering(
        self, db_session: AsyncSession, sample_waiters: list[Waiter]
    ):
        """Test that composite scores correctly rank waiters."""
        result = await db_session.execute(
            select(Waiter).order_by(Waiter.composite_score.desc())
        )
        ranked = result.scalars().all()

        # Alice should be highest, Carol lowest
        assert ranked[0].name == "Alice"
        assert ranked[-1].name == "Carol"


class TestShiftModel:
    """Tests for Shift model and active shift queries."""

    @pytest.mark.asyncio
    async def test_active_shifts(self, db_session: AsyncSession, sample_shifts: list[Shift]):
        """Test querying active (not on break) shifts."""
        result = await db_session.execute(
            select(Shift).where(Shift.status == "active")
        )
        active = result.scalars().all()

        # Alice, Bob, Carol are active; Dave is on break
        assert len(active) == 3
        waiter_ids = {s.waiter_id for s in active}

        # Dave's shift should not be in active list
        dave_shift = next(s for s in sample_shifts if s.status == "on_break")
        assert dave_shift.waiter_id not in waiter_ids

    @pytest.mark.asyncio
    async def test_shift_aggregates(self, db_session: AsyncSession, sample_shifts: list[Shift]):
        """Test that shift aggregates are tracked correctly."""
        # Bob has 3 tables served tonight
        bob_shift = next(s for s in sample_shifts if s.tables_served == 3)

        assert bob_shift.total_covers == 10
        assert bob_shift.total_tips == 62.00
        assert bob_shift.total_sales == 280.00


class TestWaitlistModel:
    """Tests for Waitlist model and queue management."""

    @pytest.mark.asyncio
    async def test_waitlist_ordering(
        self, db_session: AsyncSession, sample_waitlist: list[WaitlistEntry]
    ):
        """Test that waitlist is ordered by check-in time (FIFO)."""
        result = await db_session.execute(
            select(WaitlistEntry)
            .where(WaitlistEntry.status == "waiting")
            .order_by(WaitlistEntry.checked_in_at)
        )
        queue = result.scalars().all()

        # Johnson checked in first (10 min ago), then Smith (5 min), then Garcia (just now)
        assert queue[0].party_name == "Johnson"
        assert queue[1].party_name == "Smith"
        assert queue[2].party_name == "Garcia"

    @pytest.mark.asyncio
    async def test_seat_party_from_waitlist(
        self,
        db_session: AsyncSession,
        sample_restaurant: Restaurant,
        sample_tables: list[Table],
        sample_waiters: list[Waiter],
        sample_shifts: list[Shift],
        sample_waitlist: list[WaitlistEntry],
    ):
        """
        Real-world scenario: Seat the Johnson party from waitlist.
        1. Find their waitlist entry
        2. Create a visit
        3. Update waitlist status
        4. Update table state
        """
        # Get Johnson's waitlist entry
        johnson = next(w for w in sample_waitlist if w.party_name == "Johnson")

        # Find a booth (their preference)
        booth = next(t for t in sample_tables if t.table_type == "booth" and t.state == "clean")

        # Get Bob's shift (he's on Main Floor where booths are)
        bob_shift = next(s for s in sample_shifts if s.tables_served == 3)
        bob_waiter_id = bob_shift.waiter_id

        # Create visit
        visit = Visit(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            table_id=booth.id,
            waiter_id=bob_waiter_id,
            shift_id=bob_shift.id,
            waitlist_id=johnson.id,
            party_size=johnson.party_size,
            seated_at=datetime.utcnow(),
        )
        db_session.add(visit)

        # Update waitlist entry
        johnson.status = "seated"
        johnson.seated_at = datetime.utcnow()
        johnson.visit_id = visit.id

        # Update table state
        booth.state = "occupied"
        booth.current_visit_id = visit.id

        # Update shift stats
        bob_shift.tables_served += 1
        bob_shift.total_covers += johnson.party_size

        await db_session.commit()

        # Verify
        await db_session.refresh(johnson)
        await db_session.refresh(booth)
        await db_session.refresh(bob_shift)

        assert johnson.status == "seated"
        assert booth.state == "occupied"
        assert bob_shift.tables_served == 4


class TestVisitModel:
    """Tests for Visit model and payment tracking."""

    @pytest.mark.asyncio
    async def test_complete_visit_lifecycle(
        self,
        db_session: AsyncSession,
        sample_restaurant: Restaurant,
        sample_tables: list[Table],
        sample_shifts: list[Shift],
    ):
        """
        Real-world scenario: Complete visit from seating to payment.
        1. Create visit (party seated)
        2. Update with payment info (from POS webhook)
        3. Clear table (from ML detection)
        4. Calculate duration
        """
        table = next(t for t in sample_tables if t.state == "clean")
        shift = sample_shifts[0]

        seated_time = datetime.utcnow() - timedelta(hours=1, minutes=15)
        payment_time = datetime.utcnow() - timedelta(minutes=10)
        cleared_time = datetime.utcnow()

        visit = Visit(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            table_id=table.id,
            waiter_id=shift.waiter_id,
            shift_id=shift.id,
            party_size=4,
            seated_at=seated_time,
        )
        db_session.add(visit)
        await db_session.commit()

        # Simulate POS payment webhook
        visit.payment_at = payment_time
        visit.subtotal = 95.50
        visit.tax = 7.64
        visit.total = 103.14
        visit.tip = 20.00
        visit.tip_percentage = 20.94  # tip / subtotal * 100
        visit.pos_transaction_id = "POS_TXN_12345"

        # Simulate ML detecting cleared table
        visit.cleared_at = cleared_time
        visit.duration_minutes = int((cleared_time - seated_time).total_seconds() / 60)

        await db_session.commit()
        await db_session.refresh(visit)

        assert float(visit.total) == 103.14
        assert float(visit.tip) == 20.00
        assert visit.duration_minutes == 75  # 1 hour 15 min


class TestMenuModel:
    """Tests for Menu and OrderItem models."""

    @pytest.mark.asyncio
    async def test_create_menu_items(
        self, db_session: AsyncSession, sample_restaurant: Restaurant
    ):
        """Test creating menu items from POS data."""
        items = [
            MenuItem(
                restaurant_id=sample_restaurant.id,
                pos_item_id="burger_classic",
                name="Classic Burger",
                category="Entrees",
                price=16.00,
                cost=5.50,
            ),
            MenuItem(
                restaurant_id=sample_restaurant.id,
                pos_item_id="fries_large",
                name="Large Fries",
                category="Sides",
                price=5.50,
                cost=1.20,
            ),
        ]

        for item in items:
            db_session.add(item)
        await db_session.commit()

        result = await db_session.execute(
            select(MenuItem).where(MenuItem.restaurant_id == sample_restaurant.id)
        )
        saved = result.scalars().all()

        assert len(saved) == 2
        burger = next(i for i in saved if i.name == "Classic Burger")
        assert burger.price == 16.00
        assert burger.is_available is True
