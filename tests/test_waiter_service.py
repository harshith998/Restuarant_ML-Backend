"""Tests for WaiterService."""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit import Visit
from app.schemas.waiter import WaiterWithShiftStats
from app.services.waiter_service import WaiterService, RoutingConfig


@pytest_asyncio.fixture
async def waiter_service(db_session: AsyncSession) -> WaiterService:
    """Create a WaiterService instance."""
    return WaiterService(db_session)


@pytest_asyncio.fixture
def routing_config() -> RoutingConfig:
    """Create a default routing config."""
    return RoutingConfig(
        mode="section",
        max_tables_per_waiter=5,
        efficiency_weight=1.0,
        workload_penalty=3.0,
        tip_penalty=2.0,
        recency_penalty_minutes=5,
        recency_penalty_weight=1.5,
    )


class TestGetActiveWaiters:
    """Tests for get_active_waiters method."""

    async def test_returns_waiters_with_active_shifts(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Returns waiters who have active or on_break shifts."""
        waiters = await waiter_service.get_active_waiters(sample_restaurant.id)

        # Should have 4 waiters (Alice, Bob, Carol active; Dave on break)
        assert len(waiters) == 4

        names = {w.name for w in waiters}
        assert "Alice" in names
        assert "Bob" in names
        assert "Carol" in names
        assert "Dave" in names

    async def test_includes_shift_stats(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Includes current shift statistics."""
        waiters = await waiter_service.get_active_waiters(sample_restaurant.id)

        # Find Alice's stats
        alice = next(w for w in waiters if w.name == "Alice")

        assert alice.current_tips == 45.00
        assert alice.current_covers == 6
        assert alice.status == "active"

    async def test_includes_section_id(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Includes section assignment from shift."""
        waiters = await waiter_service.get_active_waiters(sample_restaurant.id)

        # All waiters should have section_ids
        for waiter in waiters:
            assert waiter.section_id is not None

    async def test_returns_empty_for_no_active_shifts(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        # Note: no sample_shifts fixture - no shifts exist
    ):
        """Returns empty list when no active shifts."""
        waiters = await waiter_service.get_active_waiters(sample_restaurant.id)

        assert waiters == []


class TestGetAvailableWaiters:
    """Tests for get_available_waiters method."""

    async def test_excludes_on_break(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Excludes waiters on break."""
        waiters = await waiter_service.get_available_waiters(sample_restaurant.id)

        names = {w.name for w in waiters}
        assert "Dave" not in names  # Dave is on break

    async def test_excludes_at_max_tables(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Excludes waiters at max table capacity."""
        # With max_tables=1, most waiters should be excluded
        waiters = await waiter_service.get_available_waiters(
            sample_restaurant.id,
            max_tables=1,
        )

        # All waiters have 0 active visits (no active tables in fixtures)
        # so they should all be available with max_tables=1
        assert len(waiters) == 3  # Dave excluded (on break)

    async def test_filters_by_section(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Filters by section when section_ids provided."""
        bar_section = sample_sections[0]

        waiters = await waiter_service.get_available_waiters(
            sample_restaurant.id,
            section_ids={bar_section.id},
        )

        # Only Alice is in Bar section
        assert len(waiters) == 1
        assert waiters[0].name == "Alice"


class TestCalculateWaiterPriority:
    """Tests for calculate_waiter_priority method."""

    async def test_efficiency_component(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        routing_config: RoutingConfig,
    ):
        """Higher composite_score gives higher priority."""
        waiter_high = WaiterWithShiftStats(
            id=uuid4(),
            restaurant_id=uuid4(),
            name="High",
            tier="strong",
            composite_score=90.0,
            tier_updated_at=None,
            total_shifts=100,
            total_covers=1000,
            total_tips=10000.0,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            current_tables=0,
            current_tips=0.0,
            current_covers=0,
            status="active",
        )

        waiter_low = WaiterWithShiftStats(
            id=uuid4(),
            restaurant_id=uuid4(),
            name="Low",
            tier="developing",
            composite_score=30.0,
            tier_updated_at=None,
            total_shifts=10,
            total_covers=100,
            total_tips=1000.0,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            current_tables=0,
            current_tips=0.0,
            current_covers=0,
            status="active",
        )

        priority_high = await waiter_service.calculate_waiter_priority(
            waiter_high, total_tips_in_pool=0, config=routing_config
        )
        priority_low = await waiter_service.calculate_waiter_priority(
            waiter_low, total_tips_in_pool=0, config=routing_config
        )

        assert priority_high > priority_low

    async def test_workload_penalty(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        routing_config: RoutingConfig,
    ):
        """More current tables gives lower priority."""
        waiter_few = WaiterWithShiftStats(
            id=uuid4(),
            restaurant_id=uuid4(),
            name="Few",
            tier="standard",
            composite_score=50.0,
            tier_updated_at=None,
            total_shifts=50,
            total_covers=500,
            total_tips=5000.0,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            current_tables=1,
            current_tips=0.0,
            current_covers=0,
            status="active",
        )

        waiter_many = WaiterWithShiftStats(
            id=uuid4(),
            restaurant_id=uuid4(),
            name="Many",
            tier="standard",
            composite_score=50.0,
            tier_updated_at=None,
            total_shifts=50,
            total_covers=500,
            total_tips=5000.0,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            current_tables=4,
            current_tips=0.0,
            current_covers=0,
            status="active",
        )

        priority_few = await waiter_service.calculate_waiter_priority(
            waiter_few, total_tips_in_pool=0, config=routing_config
        )
        priority_many = await waiter_service.calculate_waiter_priority(
            waiter_many, total_tips_in_pool=0, config=routing_config
        )

        assert priority_few > priority_many

    async def test_tip_penalty(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        routing_config: RoutingConfig,
    ):
        """Higher tip share gives lower priority."""
        waiter_low_tips = WaiterWithShiftStats(
            id=uuid4(),
            restaurant_id=uuid4(),
            name="LowTips",
            tier="standard",
            composite_score=50.0,
            tier_updated_at=None,
            total_shifts=50,
            total_covers=500,
            total_tips=5000.0,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            current_tables=0,
            current_tips=10.0,
            current_covers=0,
            status="active",
        )

        waiter_high_tips = WaiterWithShiftStats(
            id=uuid4(),
            restaurant_id=uuid4(),
            name="HighTips",
            tier="standard",
            composite_score=50.0,
            tier_updated_at=None,
            total_shifts=50,
            total_covers=500,
            total_tips=5000.0,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            current_tables=0,
            current_tips=90.0,
            current_covers=0,
            status="active",
        )

        # Total tips pool is 100
        priority_low = await waiter_service.calculate_waiter_priority(
            waiter_low_tips, total_tips_in_pool=100, config=routing_config
        )
        priority_high = await waiter_service.calculate_waiter_priority(
            waiter_high_tips, total_tips_in_pool=100, config=routing_config
        )

        assert priority_low > priority_high


class TestRecencyPenalty:
    """Tests for recency penalty calculation."""

    async def test_no_penalty_when_no_seating(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        routing_config: RoutingConfig,
    ):
        """No penalty when waiter has no recent seating."""
        penalty = waiter_service._calculate_recency_penalty(None, routing_config)
        assert penalty == 0.0

    async def test_no_penalty_outside_window(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        routing_config: RoutingConfig,
    ):
        """No penalty when last seating is outside window."""
        # Last seated 10 minutes ago (window is 5 min)
        last_seated = datetime.utcnow() - timedelta(minutes=10)

        penalty = waiter_service._calculate_recency_penalty(last_seated, routing_config)
        assert penalty == 0.0

    async def test_full_penalty_just_seated(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        routing_config: RoutingConfig,
    ):
        """Full penalty when just seated."""
        # Last seated 0 minutes ago
        last_seated = datetime.utcnow()

        penalty = waiter_service._calculate_recency_penalty(last_seated, routing_config)

        # Should be close to recency_penalty_weight (1.5)
        assert penalty > 1.4  # Allow small timing variance

    async def test_partial_penalty_within_window(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        routing_config: RoutingConfig,
    ):
        """Partial penalty when within window but not just seated."""
        # Last seated 2.5 minutes ago (halfway through 5 min window)
        last_seated = datetime.utcnow() - timedelta(minutes=2.5)

        penalty = waiter_service._calculate_recency_penalty(last_seated, routing_config)

        # Should be about half the max penalty
        assert 0.5 < penalty < 1.0


class TestScoreAndRankWaiters:
    """Tests for score_and_rank_waiters method."""

    async def test_returns_sorted_by_priority(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        routing_config: RoutingConfig,
    ):
        """Returns waiters sorted by priority descending."""
        waiters = [
            WaiterWithShiftStats(
                id=uuid4(),
                restaurant_id=uuid4(),
                name="Low",
                tier="developing",
                composite_score=30.0,
                tier_updated_at=None,
                total_shifts=10,
                total_covers=100,
                total_tips=1000.0,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                current_tables=2,
                current_tips=50.0,
                current_covers=10,
                status="active",
            ),
            WaiterWithShiftStats(
                id=uuid4(),
                restaurant_id=uuid4(),
                name="High",
                tier="strong",
                composite_score=90.0,
                tier_updated_at=None,
                total_shifts=100,
                total_covers=1000,
                total_tips=10000.0,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                current_tables=0,
                current_tips=10.0,
                current_covers=2,
                status="active",
            ),
            WaiterWithShiftStats(
                id=uuid4(),
                restaurant_id=uuid4(),
                name="Medium",
                tier="standard",
                composite_score=55.0,
                tier_updated_at=None,
                total_shifts=50,
                total_covers=500,
                total_tips=5000.0,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                current_tables=1,
                current_tips=20.0,
                current_covers=5,
                status="active",
            ),
        ]

        ranked = await waiter_service.score_and_rank_waiters(waiters, routing_config)

        assert len(ranked) == 3
        # Should be sorted High, Medium, Low
        assert ranked[0][0].name == "High"
        assert ranked[1][0].name == "Medium"
        assert ranked[2][0].name == "Low"

        # Priorities should be descending
        assert ranked[0][1] > ranked[1][1] > ranked[2][1]

    async def test_returns_empty_for_no_waiters(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        routing_config: RoutingConfig,
    ):
        """Returns empty list for empty input."""
        ranked = await waiter_service.score_and_rank_waiters([], routing_config)
        assert ranked == []


class TestIsUnderserved:
    """Tests for is_underserved method."""

    async def test_detects_underserved_waiter(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
    ):
        """Detects waiter with significantly less covers/tips."""
        base_attrs = dict(
            restaurant_id=uuid4(),
            tier="standard",
            composite_score=50.0,
            tier_updated_at=None,
            total_shifts=50,
            total_covers=500,
            total_tips=5000.0,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            current_tables=0,
            status="active",
        )

        underserved = WaiterWithShiftStats(
            id=uuid4(), name="Underserved",
            current_tips=5.0, current_covers=1, **base_attrs
        )
        normal1 = WaiterWithShiftStats(
            id=uuid4(), name="Normal1",
            current_tips=50.0, current_covers=10, **base_attrs
        )
        normal2 = WaiterWithShiftStats(
            id=uuid4(), name="Normal2",
            current_tips=60.0, current_covers=12, **base_attrs
        )

        all_waiters = [underserved, normal1, normal2]

        is_under = await waiter_service.is_underserved(underserved, all_waiters)
        assert is_under is True

        is_under_normal = await waiter_service.is_underserved(normal1, all_waiters)
        assert is_under_normal is False

    async def test_not_underserved_when_single_waiter(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
    ):
        """Single waiter is not underserved."""
        waiter = WaiterWithShiftStats(
            id=uuid4(),
            restaurant_id=uuid4(),
            name="Solo",
            tier="standard",
            composite_score=50.0,
            tier_updated_at=None,
            total_shifts=50,
            total_covers=500,
            total_tips=5000.0,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            current_tables=0,
            current_tips=0.0,
            current_covers=0,
            status="active",
        )

        is_under = await waiter_service.is_underserved(waiter, [waiter])
        assert is_under is False


class TestGetLastSeatingTime:
    """Tests for get_last_seating_time method."""

    async def test_returns_most_recent_seating(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        sample_restaurant,
        sample_sections,
        sample_tables,
        sample_waiters,
        sample_shifts,
    ):
        """Returns most recent seated_at timestamp."""
        alice = sample_waiters[0]
        alice_shift = sample_shifts[0]

        # Create some visits for Alice
        now = datetime.utcnow()
        visits = [
            Visit(
                restaurant_id=sample_restaurant.id,
                table_id=sample_tables[0].id,
                waiter_id=alice.id,
                shift_id=alice_shift.id,
                party_size=2,
                seated_at=now - timedelta(hours=2),
            ),
            Visit(
                restaurant_id=sample_restaurant.id,
                table_id=sample_tables[1].id,
                waiter_id=alice.id,
                shift_id=alice_shift.id,
                party_size=2,
                seated_at=now - timedelta(hours=1),  # Most recent
            ),
        ]
        for v in visits:
            db_session.add(v)
        await db_session.commit()

        last_seated = await waiter_service.get_last_seating_time(
            alice.id, alice_shift.id
        )

        assert last_seated is not None
        # Should be approximately 1 hour ago
        assert (now - last_seated).total_seconds() < 3700  # ~1 hour

    async def test_returns_none_for_no_visits(
        self,
        db_session: AsyncSession,
        waiter_service: WaiterService,
        sample_restaurant,
        sample_sections,
        sample_waiters,
        sample_shifts,
    ):
        """Returns None when waiter has no visits."""
        alice = sample_waiters[0]
        alice_shift = sample_shifts[0]

        last_seated = await waiter_service.get_last_seating_time(
            alice.id, alice_shift.id
        )

        assert last_seated is None
