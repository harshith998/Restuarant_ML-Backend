"""Tests for RoutingService."""
from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.routing_service import RoutingService, ScoredTable
from app.models.table import Table
from app.models.waitlist import WaitlistEntry


@pytest_asyncio.fixture
async def routing_service(db_session: AsyncSession) -> RoutingService:
    """Create a RoutingService instance."""
    return RoutingService(db_session)


class TestTableScoring:
    """Tests for table scoring algorithm."""

    async def test_scores_type_match(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Boosts score when table type matches preference."""
        # Filter to booth tables only for clear comparison
        booths = [t for t in sample_tables if t.table_type == "booth" and t.state == "clean"]

        scored = routing_service._score_tables(
            tables=booths,
            party_size=4,
            table_preference="booth",
            location_preference=None,
        )

        assert len(scored) > 0
        assert all(st.type_matched for st in scored)

    async def test_scores_location_match(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Boosts score when location matches preference."""
        # Filter to patio tables
        patio_tables = [t for t in sample_tables if t.location == "patio" and t.state == "clean"]

        scored = routing_service._score_tables(
            tables=patio_tables,
            party_size=4,
            table_preference=None,
            location_preference="patio",
        )

        assert len(scored) > 0
        assert all(st.location_matched for st in scored)

    async def test_penalizes_excess_capacity(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Smaller tables score higher for same party size."""
        # Get tables with different capacities
        small_table = [t for t in sample_tables if t.capacity == 4 and t.state == "clean"][0]
        large_table = [t for t in sample_tables if t.capacity == 6 and t.state == "clean"][0]

        scored = routing_service._score_tables(
            tables=[small_table, large_table],
            party_size=4,
            table_preference=None,
            location_preference=None,
        )

        # Smaller table should have higher score (less wasted capacity)
        small_scored = next(st for st in scored if st.table.id == small_table.id)
        large_scored = next(st for st in scored if st.table.id == large_table.id)

        assert small_scored.score > large_scored.score

    async def test_combined_scoring(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Both type and location match give highest score."""
        # Booth tables inside
        booths_inside = [t for t in sample_tables
                        if t.table_type == "booth" and t.location == "inside" and t.state == "clean"]
        # Regular tables inside
        tables_inside = [t for t in sample_tables
                        if t.table_type == "table" and t.location == "inside" and t.state == "clean"]

        if booths_inside and tables_inside:
            scored = routing_service._score_tables(
                tables=booths_inside + tables_inside,
                party_size=4,
                table_preference="booth",
                location_preference="inside",
            )

            # Booth should score higher (matches type preference)
            booth_scored = [st for st in scored if st.table.table_type == "booth"]
            table_scored = [st for st in scored if st.table.table_type == "table"]

            if booth_scored and table_scored:
                assert booth_scored[0].score >= table_scored[0].score


class TestRoutePartySectionMode:
    """Tests for section mode routing."""

    async def test_routes_to_available_table(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
        sample_waiters,
        sample_shifts,
    ):
        """Routes party to an available table with assigned waiter."""
        result = await routing_service.route_party(
            restaurant_id=sample_restaurant.id,
            party_size=4,
        )

        assert result.success is True
        assert result.table_id is not None
        assert result.waiter_id is not None
        assert result.table_number is not None

    async def test_respects_party_size(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
        sample_waiters,
        sample_shifts,
    ):
        """Only assigns tables that can fit the party."""
        result = await routing_service.route_party(
            restaurant_id=sample_restaurant.id,
            party_size=5,
        )

        if result.success:
            assert result.table_capacity >= 5

    async def test_returns_match_details(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
        sample_waiters,
        sample_shifts,
    ):
        """Includes match details in response."""
        result = await routing_service.route_party(
            restaurant_id=sample_restaurant.id,
            party_size=4,
            table_preference="booth",
        )

        if result.success:
            assert result.match_details is not None
            assert hasattr(result.match_details, "type_matched")
            assert hasattr(result.match_details, "location_matched")

    async def test_fails_for_unknown_restaurant(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
    ):
        """Returns failure for non-existent restaurant."""
        result = await routing_service.route_party(
            restaurant_id=uuid4(),
            party_size=4,
        )

        assert result.success is False
        assert "not found" in result.message.lower()

    async def test_fails_when_no_tables_available(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
        sample_waiters,
        sample_shifts,
    ):
        """Returns failure when no tables can fit party."""
        # Request a party too large for any table
        result = await routing_service.route_party(
            restaurant_id=sample_restaurant.id,
            party_size=20,
        )

        assert result.success is False
        assert "no available" in result.message.lower()

    async def test_requires_party_size(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Returns failure when party_size not provided and no waitlist_id."""
        result = await routing_service.route_party(
            restaurant_id=sample_restaurant.id,
            party_size=None,
        )

        assert result.success is False
        assert "party_size" in result.message.lower()


class TestRoutePartyRotationMode:
    """Tests for rotation mode routing."""

    async def test_routes_ignoring_sections(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
        sample_waiters,
        sample_shifts,
    ):
        """In rotation mode, any waiter can be assigned to any table."""
        # Switch to rotation mode
        await routing_service.switch_mode(sample_restaurant.id, "rotation")

        result = await routing_service.route_party(
            restaurant_id=sample_restaurant.id,
            party_size=4,
        )

        assert result.success is True
        assert result.waiter_id is not None

    async def test_picks_best_table_any_section(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
        sample_waiters,
        sample_shifts,
    ):
        """Selects best scoring table regardless of section."""
        await routing_service.switch_mode(sample_restaurant.id, "rotation")

        result = await routing_service.route_party(
            restaurant_id=sample_restaurant.id,
            party_size=4,
            table_preference="booth",
        )

        if result.success:
            # If booth was available and selected, type should match
            if result.table_type == "booth":
                assert result.match_details.type_matched is True


class TestWaitlistIntegration:
    """Tests for routing from waitlist."""

    async def test_uses_waitlist_preferences(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
        sample_waiters,
        sample_shifts,
        sample_waitlist,
    ):
        """Uses waitlist entry's preferences for routing."""
        # Johnson party wants a booth
        johnson = sample_waitlist[0]

        result = await routing_service.route_party(
            restaurant_id=sample_restaurant.id,
            waitlist_id=johnson.id,
        )

        assert result.success is True
        # Should attempt to match booth preference
        assert result.match_details is not None

    async def test_uses_waitlist_party_size(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
        sample_waiters,
        sample_shifts,
        sample_waitlist,
    ):
        """Uses party size from waitlist entry."""
        smith = sample_waitlist[1]  # Party of 2

        result = await routing_service.route_party(
            restaurant_id=sample_restaurant.id,
            waitlist_id=smith.id,
        )

        if result.success:
            assert result.table_capacity >= 2

    async def test_fails_for_invalid_waitlist(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
    ):
        """Returns failure for non-existent waitlist entry."""
        result = await routing_service.route_party(
            restaurant_id=sample_restaurant.id,
            waitlist_id=uuid4(),
        )

        assert result.success is False
        assert "not found" in result.message.lower()


class TestSeatParty:
    """Tests for seat_party method."""

    async def test_creates_visit(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
        sample_waiters,
        sample_shifts,
    ):
        """Creates a Visit record when seating party."""
        # First route to get valid table/waiter
        route_result = await routing_service.route_party(
            restaurant_id=sample_restaurant.id,
            party_size=4,
        )

        assert route_result.success

        visit = await routing_service.seat_party(
            restaurant_id=sample_restaurant.id,
            table_id=route_result.table_id,
            waiter_id=route_result.waiter_id,
            party_size=4,
        )

        assert visit is not None
        assert visit.party_size == 4
        assert visit.table_id == route_result.table_id
        assert visit.waiter_id == route_result.waiter_id

    async def test_updates_table_state(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
        sample_waiters,
        sample_shifts,
    ):
        """Sets table to occupied after seating."""
        route_result = await routing_service.route_party(
            restaurant_id=sample_restaurant.id,
            party_size=4,
        )

        assert route_result.success

        # Get table before
        table = next(t for t in sample_tables if t.id == route_result.table_id)

        await routing_service.seat_party(
            restaurant_id=sample_restaurant.id,
            table_id=route_result.table_id,
            waiter_id=route_result.waiter_id,
            party_size=4,
        )

        await db_session.refresh(table)
        assert table.state == "occupied"

    async def test_raises_for_waiter_without_shift(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
        sample_sections,
        sample_tables,
        sample_waiters,
    ):
        """Raises error if waiter has no active shift."""
        from app.models.waiter import Waiter

        # Create waiter with no shift
        new_waiter = Waiter(
            id=uuid4(),
            restaurant_id=sample_restaurant.id,
            name="NoShift",
            tier="standard",
            composite_score=50.0,
        )
        db_session.add(new_waiter)
        await db_session.commit()

        table = [t for t in sample_tables if t.state == "clean"][0]

        with pytest.raises(ValueError, match="no active shift"):
            await routing_service.seat_party(
                restaurant_id=sample_restaurant.id,
                table_id=table.id,
                waiter_id=new_waiter.id,
                party_size=4,
            )


class TestSwitchMode:
    """Tests for switch_mode method."""

    async def test_switches_to_rotation(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
    ):
        """Switches mode to rotation."""
        result = await routing_service.switch_mode(
            sample_restaurant.id,
            "rotation",
        )

        assert result is True

        await db_session.refresh(sample_restaurant)
        assert sample_restaurant.config["routing"]["mode"] == "rotation"

    async def test_switches_to_section(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
    ):
        """Switches mode to section."""
        # First switch to rotation
        await routing_service.switch_mode(sample_restaurant.id, "rotation")

        # Then back to section
        result = await routing_service.switch_mode(
            sample_restaurant.id,
            "section",
        )

        assert result is True

        await db_session.refresh(sample_restaurant)
        assert sample_restaurant.config["routing"]["mode"] == "section"

    async def test_raises_for_invalid_mode(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
        sample_restaurant,
    ):
        """Raises error for invalid mode."""
        with pytest.raises(ValueError, match="Invalid mode"):
            await routing_service.switch_mode(
                sample_restaurant.id,
                "invalid_mode",
            )

    async def test_raises_for_invalid_restaurant(
        self,
        db_session: AsyncSession,
        routing_service: RoutingService,
    ):
        """Raises error for non-existent restaurant."""
        with pytest.raises(ValueError, match="not found"):
            await routing_service.switch_mode(
                uuid4(),
                "rotation",
            )
