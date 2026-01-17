"""Tests for TableService."""
from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.table import Table
from app.models.metrics import TableStateLog
from app.services.table_service import TableService


@pytest_asyncio.fixture
async def table_service(db_session: AsyncSession) -> TableService:
    """Create a TableService instance."""
    return TableService(db_session)


class TestGetAvailableTables:
    """Tests for get_available_tables method."""

    async def test_filters_by_clean_state(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Only returns tables with state='clean'."""
        tables = await table_service.get_available_tables(
            restaurant_id=sample_restaurant.id,
            min_capacity=1,
        )

        # All returned tables should be clean
        for table in tables:
            assert table.state == "clean"

        # Check we excluded occupied/dirty/unavailable tables
        table_numbers = {t.table_number for t in tables}
        assert "B4" not in table_numbers  # occupied
        assert "T2" not in table_numbers  # dirty
        assert "P3" not in table_numbers  # unavailable

    async def test_filters_by_capacity(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Only returns tables with capacity >= min_capacity."""
        # Request tables for party of 4
        tables = await table_service.get_available_tables(
            restaurant_id=sample_restaurant.id,
            min_capacity=4,
        )

        # All returned tables should fit party of 4
        for table in tables:
            assert table.capacity >= 4

        # Bar tables (capacity=2) should not be included
        table_numbers = {t.table_number for t in tables}
        assert "B1" not in table_numbers
        assert "B2" not in table_numbers
        assert "B3" not in table_numbers

    async def test_filters_by_preference(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Filters by table_type when preference is provided."""
        # Request booth tables
        tables = await table_service.get_available_tables(
            restaurant_id=sample_restaurant.id,
            min_capacity=1,
            preference="booth",
        )

        # All returned tables should be booths
        assert len(tables) > 0
        for table in tables:
            assert table.table_type == "booth"

    async def test_no_preference_returns_all_types(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Returns all table types when preference is 'none' or None."""
        tables = await table_service.get_available_tables(
            restaurant_id=sample_restaurant.id,
            min_capacity=1,
            preference="none",
        )

        # Should have multiple table types
        types = {t.table_type for t in tables}
        assert len(types) > 1

    async def test_sorted_by_capacity(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Returns tables sorted by capacity (smallest first)."""
        tables = await table_service.get_available_tables(
            restaurant_id=sample_restaurant.id,
            min_capacity=1,
        )

        capacities = [t.capacity for t in tables]
        assert capacities == sorted(capacities)

    async def test_returns_empty_when_no_match(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Returns empty list when no tables match criteria."""
        # Request party of 100 - no table fits
        tables = await table_service.get_available_tables(
            restaurant_id=sample_restaurant.id,
            min_capacity=100,
        )

        assert tables == []


class TestUpdateTableState:
    """Tests for update_table_state method."""

    async def test_updates_state(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Updates table state successfully."""
        table = sample_tables[0]  # B1 - clean

        updated = await table_service.update_table_state(
            table_id=table.id,
            state="occupied",
            source="host",
        )

        assert updated.state == "occupied"
        assert updated.state_updated_at is not None

    async def test_creates_log_entry(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Creates TableStateLog entry for state change."""
        table = sample_tables[0]  # B1 - clean
        original_state = table.state

        await table_service.update_table_state(
            table_id=table.id,
            state="dirty",
            source="ml",
            confidence=0.95,
        )

        # Check log was created
        from sqlalchemy import select
        stmt = select(TableStateLog).where(TableStateLog.table_id == table.id)
        result = await db_session.execute(stmt)
        logs = result.scalars().all()

        assert len(logs) >= 1
        latest_log = logs[-1]
        assert latest_log.previous_state == original_state
        assert latest_log.new_state == "dirty"
        assert latest_log.source == "ml"
        assert float(latest_log.confidence) == 0.95

    async def test_raises_for_invalid_table(
        self,
        db_session: AsyncSession,
        table_service: TableService,
    ):
        """Raises ValueError for non-existent table."""
        with pytest.raises(ValueError, match="not found"):
            await table_service.update_table_state(
                table_id=uuid4(),
                state="clean",
                source="host",
            )


class TestGetFloorStatus:
    """Tests for get_floor_status method."""

    async def test_returns_all_active_tables(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Returns all active tables for restaurant."""
        floor_status = await table_service.get_floor_status(
            restaurant_id=sample_restaurant.id,
        )

        # Should have all 13 tables
        assert len(floor_status) == 13

    async def test_includes_section_info(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Includes section name in floor status."""
        floor_status = await table_service.get_floor_status(
            restaurant_id=sample_restaurant.id,
        )

        # All tables should have section info
        for table_info in floor_status:
            assert "section_name" in table_info
            assert table_info["section_name"] in ["Bar", "Main Floor", "Patio"]

    async def test_includes_current_state(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Includes current state for each table."""
        floor_status = await table_service.get_floor_status(
            restaurant_id=sample_restaurant.id,
        )

        states = {t["state"] for t in floor_status}
        # Should have mix of states based on fixtures
        assert "clean" in states
        assert "occupied" in states


class TestSeatTable:
    """Tests for seat_table method."""

    async def test_marks_table_occupied(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Marks table as occupied when seated."""
        table = sample_tables[0]  # B1 - clean
        visit_id = uuid4()

        updated = await table_service.seat_table(
            table_id=table.id,
            visit_id=visit_id,
        )

        assert updated.state == "occupied"
        assert updated.current_visit_id == visit_id

    async def test_creates_log_entry(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Creates log entry when seating."""
        table = sample_tables[0]  # B1 - clean
        visit_id = uuid4()

        await table_service.seat_table(
            table_id=table.id,
            visit_id=visit_id,
        )

        # Check log was created
        from sqlalchemy import select
        stmt = select(TableStateLog).where(TableStateLog.table_id == table.id)
        result = await db_session.execute(stmt)
        logs = result.scalars().all()

        assert len(logs) >= 1
        latest_log = logs[-1]
        assert latest_log.new_state == "occupied"
        assert latest_log.source == "system"


class TestClearTable:
    """Tests for clear_table method."""

    async def test_marks_table_dirty(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Marks table as dirty when cleared."""
        # First seat the table
        table = sample_tables[0]
        visit_id = uuid4()
        await table_service.seat_table(table_id=table.id, visit_id=visit_id)

        # Now clear it
        updated = await table_service.clear_table(table_id=table.id)

        assert updated.state == "dirty"
        assert updated.current_visit_id is None

    async def test_creates_log_entry(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Creates log entry when clearing."""
        # First seat the table
        table = sample_tables[0]
        visit_id = uuid4()
        await table_service.seat_table(table_id=table.id, visit_id=visit_id)

        # Now clear it
        await table_service.clear_table(table_id=table.id)

        # Check log was created
        from sqlalchemy import select
        stmt = select(TableStateLog).where(
            TableStateLog.table_id == table.id
        ).where(
            TableStateLog.new_state == "dirty"
        )
        result = await db_session.execute(stmt)
        log = result.scalar_one_or_none()

        assert log is not None
        assert log.previous_state == "occupied"


class TestGetSectionsFromTables:
    """Tests for get_sections_from_tables method."""

    async def test_extracts_unique_sections(
        self,
        db_session: AsyncSession,
        table_service: TableService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Extracts unique section IDs from tables."""
        sections = await table_service.get_sections_from_tables(sample_tables)

        # Should have 3 unique sections
        assert len(sections) == 3

    async def test_handles_empty_list(
        self,
        db_session: AsyncSession,
        table_service: TableService,
    ):
        """Returns empty set for empty table list."""
        sections = await table_service.get_sections_from_tables([])

        assert sections == set()
