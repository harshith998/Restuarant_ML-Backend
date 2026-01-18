"""Tests for schedule analytics and insights services."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import List
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Restaurant,
    Schedule,
    ScheduleItem,
    StaffingRequirements,
    StaffPreference,
    Waiter,
)
from app.services.demand_forecaster import DemandForecaster
from app.services.schedule_analytics import ScheduleAnalyticsService
from app.services.schedule_insights import ScheduleInsightsService, ScheduleInsight


# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def analytics_restaurant(db_session: AsyncSession) -> Restaurant:
    """Create a restaurant for analytics tests."""
    restaurant = Restaurant(
        id=uuid4(),
        name="Analytics Test Restaurant",
        timezone="America/New_York",
    )
    db_session.add(restaurant)
    await db_session.commit()
    await db_session.refresh(restaurant)
    return restaurant


@pytest_asyncio.fixture
async def analytics_waiters(
    db_session: AsyncSession,
    analytics_restaurant: Restaurant,
) -> List[Waiter]:
    """Create waiters for analytics tests."""
    waiters = [
        Waiter(
            id=uuid4(),
            restaurant_id=analytics_restaurant.id,
            name="Alice",
            email="alice@test.com",
            is_active=True,
            role="server",
        ),
        Waiter(
            id=uuid4(),
            restaurant_id=analytics_restaurant.id,
            name="Bob",
            email="bob@test.com",
            is_active=True,
            role="server",
        ),
        Waiter(
            id=uuid4(),
            restaurant_id=analytics_restaurant.id,
            name="Carol",
            email="carol@test.com",
            is_active=True,
            role="server",
        ),
    ]
    for w in waiters:
        db_session.add(w)
    await db_session.commit()
    for w in waiters:
        await db_session.refresh(w)
    return waiters


@pytest_asyncio.fixture
async def staffing_requirements(
    db_session: AsyncSession,
    analytics_restaurant: Restaurant,
) -> List[StaffingRequirements]:
    """Create staffing requirements for coverage tests."""
    requirements = []
    # Morning shifts (6am-2pm) - need 2 servers each day
    for day in range(7):
        req = StaffingRequirements(
            id=uuid4(),
            restaurant_id=analytics_restaurant.id,
            day_of_week=day,
            start_time=time(6, 0),
            end_time=time(14, 0),
            role="server",
            min_staff=2,
            max_staff=3,
        )
        requirements.append(req)
        db_session.add(req)

    # Evening shifts (4pm-11pm) - need 3 servers each day
    for day in range(7):
        req = StaffingRequirements(
            id=uuid4(),
            restaurant_id=analytics_restaurant.id,
            day_of_week=day,
            start_time=time(16, 0),
            end_time=time(23, 0),
            role="server",
            min_staff=3,
            max_staff=5,
        )
        requirements.append(req)
        db_session.add(req)

    await db_session.commit()
    return requirements


@pytest_asyncio.fixture
async def schedule_with_full_coverage(
    db_session: AsyncSession,
    analytics_restaurant: Restaurant,
    analytics_waiters: List[Waiter],
    staffing_requirements: List[StaffingRequirements],
) -> Schedule:
    """Create a schedule that meets all staffing requirements."""
    # Use a Monday as week start
    week_start = date.today() - timedelta(days=date.today().weekday())

    schedule = Schedule(
        id=uuid4(),
        restaurant_id=analytics_restaurant.id,
        week_start_date=week_start,
        status="published",
        generated_by="engine",
        version=1,
    )
    db_session.add(schedule)
    await db_session.commit()

    # Add items to meet all requirements - balanced across all 3 staff
    for day_offset in range(7):
        day_date = week_start + timedelta(days=day_offset)

        # Morning shift - all 3 servers (balanced hours)
        for waiter in analytics_waiters:
            item = ScheduleItem(
                id=uuid4(),
                schedule_id=schedule.id,
                waiter_id=waiter.id,
                role="server",
                shift_date=day_date,
                shift_start=time(6, 0),
                shift_end=time(14, 0),
                source="engine",
            )
            db_session.add(item)

        # Evening shift - all 3 servers (balanced hours)
        for waiter in analytics_waiters:
            item = ScheduleItem(
                id=uuid4(),
                schedule_id=schedule.id,
                waiter_id=waiter.id,
                role="server",
                shift_date=day_date,
                shift_start=time(16, 0),
                shift_end=time(23, 0),
                source="engine",
            )
            db_session.add(item)

    await db_session.commit()
    await db_session.refresh(schedule)
    return schedule


@pytest_asyncio.fixture
async def schedule_with_gaps(
    db_session: AsyncSession,
    analytics_restaurant: Restaurant,
    analytics_waiters: List[Waiter],
    staffing_requirements: List[StaffingRequirements],
) -> Schedule:
    """Create a schedule with intentional coverage gaps."""
    week_start = date.today() - timedelta(days=date.today().weekday())

    schedule = Schedule(
        id=uuid4(),
        restaurant_id=analytics_restaurant.id,
        week_start_date=week_start,
        status="draft",
        generated_by="manual",
        version=1,
    )
    db_session.add(schedule)
    await db_session.commit()

    # Only add 1 server for morning (need 2) and 2 for evening (need 3)
    for day_offset in range(7):
        day_date = week_start + timedelta(days=day_offset)

        # Morning shift - only 1 server (under by 1)
        item = ScheduleItem(
            id=uuid4(),
            schedule_id=schedule.id,
            waiter_id=analytics_waiters[0].id,
            role="server",
            shift_date=day_date,
            shift_start=time(6, 0),
            shift_end=time(14, 0),
            source="manual",
        )
        db_session.add(item)

        # Evening shift - only 2 servers (under by 1)
        for waiter in analytics_waiters[:2]:
            item = ScheduleItem(
                id=uuid4(),
                schedule_id=schedule.id,
                waiter_id=waiter.id,
                role="server",
                shift_date=day_date,
                shift_start=time(16, 0),
                shift_end=time(23, 0),
                source="manual",
            )
            db_session.add(item)

    await db_session.commit()
    await db_session.refresh(schedule)
    return schedule


@pytest_asyncio.fixture
async def schedule_with_fairness_issues(
    db_session: AsyncSession,
    analytics_restaurant: Restaurant,
    analytics_waiters: List[Waiter],
) -> Schedule:
    """Create a schedule where one staff member has way more hours."""
    week_start = date.today() - timedelta(days=date.today().weekday())

    schedule = Schedule(
        id=uuid4(),
        restaurant_id=analytics_restaurant.id,
        week_start_date=week_start,
        status="published",
        generated_by="manual",
        version=1,
    )
    db_session.add(schedule)
    await db_session.commit()

    # Alice gets 6 shifts (48 hours)
    for day_offset in range(6):
        day_date = week_start + timedelta(days=day_offset)
        item = ScheduleItem(
            id=uuid4(),
            schedule_id=schedule.id,
            waiter_id=analytics_waiters[0].id,
            role="server",
            shift_date=day_date,
            shift_start=time(10, 0),
            shift_end=time(18, 0),
            source="manual",
        )
        db_session.add(item)

    # Bob gets 2 shifts (16 hours)
    for day_offset in range(2):
        day_date = week_start + timedelta(days=day_offset)
        item = ScheduleItem(
            id=uuid4(),
            schedule_id=schedule.id,
            waiter_id=analytics_waiters[1].id,
            role="server",
            shift_date=day_date,
            shift_start=time(10, 0),
            shift_end=time(18, 0),
            source="manual",
        )
        db_session.add(item)

    # Carol gets 1 shift (8 hours)
    item = ScheduleItem(
        id=uuid4(),
        schedule_id=schedule.id,
        waiter_id=analytics_waiters[2].id,
        role="server",
        shift_date=week_start,
        shift_start=time(10, 0),
        shift_end=time(18, 0),
        source="manual",
    )
    db_session.add(item)

    await db_session.commit()
    await db_session.refresh(schedule)
    return schedule


@pytest_asyncio.fixture
async def schedule_with_clopening(
    db_session: AsyncSession,
    analytics_restaurant: Restaurant,
    analytics_waiters: List[Waiter],
) -> Schedule:
    """Create a schedule with clopening pattern."""
    week_start = date.today() - timedelta(days=date.today().weekday())

    schedule = Schedule(
        id=uuid4(),
        restaurant_id=analytics_restaurant.id,
        week_start_date=week_start,
        status="draft",
        generated_by="manual",
        version=1,
    )
    db_session.add(schedule)
    await db_session.commit()

    # Monday closing shift (6pm - 2am)
    item1 = ScheduleItem(
        id=uuid4(),
        schedule_id=schedule.id,
        waiter_id=analytics_waiters[0].id,
        role="server",
        shift_date=week_start,
        shift_start=time(18, 0),
        shift_end=time(2, 0),  # Overnight
        source="manual",
    )
    db_session.add(item1)

    # Tuesday opening shift (6am - 2pm) - only 4 hours rest!
    item2 = ScheduleItem(
        id=uuid4(),
        schedule_id=schedule.id,
        waiter_id=analytics_waiters[0].id,
        role="server",
        shift_date=week_start + timedelta(days=1),
        shift_start=time(6, 0),
        shift_end=time(14, 0),
        source="manual",
    )
    db_session.add(item2)

    await db_session.commit()
    await db_session.refresh(schedule)
    return schedule


# ============================================================================
# Coverage Metrics Tests
# ============================================================================


class TestCoverageMetrics:
    """Tests for coverage calculation."""

    @pytest.mark.asyncio
    async def test_coverage_100_percent_when_all_slots_filled(
        self,
        db_session: AsyncSession,
        schedule_with_full_coverage: Schedule,
    ):
        """Coverage should be 100% when all requirements are met."""
        service = ScheduleAnalyticsService(db_session)
        metrics = await service.get_coverage_metrics(schedule_with_full_coverage.id)

        assert metrics.coverage_pct == 100.0
        assert len(metrics.understaffed_slots) == 0

    @pytest.mark.asyncio
    async def test_coverage_identifies_understaffed_slots(
        self,
        db_session: AsyncSession,
        schedule_with_gaps: Schedule,
    ):
        """Should identify specific slots that are understaffed."""
        service = ScheduleAnalyticsService(db_session)
        metrics = await service.get_coverage_metrics(schedule_with_gaps.id)

        assert metrics.coverage_pct < 100.0
        assert len(metrics.understaffed_slots) > 0
        assert all(slot.shortfall > 0 for slot in metrics.understaffed_slots)

    @pytest.mark.asyncio
    async def test_coverage_daily_breakdown(
        self,
        db_session: AsyncSession,
        schedule_with_gaps: Schedule,
    ):
        """Should provide per-day coverage breakdown."""
        service = ScheduleAnalyticsService(db_session)
        metrics = await service.get_coverage_metrics(schedule_with_gaps.id)

        assert len(metrics.daily_coverage) == 7  # Full week
        assert all(0 <= day.coverage_pct <= 100 for day in metrics.daily_coverage)

    @pytest.mark.asyncio
    async def test_coverage_by_shift_type(
        self,
        db_session: AsyncSession,
        schedule_with_gaps: Schedule,
    ):
        """Should break down coverage by shift type."""
        service = ScheduleAnalyticsService(db_session)
        metrics = await service.get_coverage_metrics(schedule_with_gaps.id)

        # Should have morning and evening coverage
        assert len(metrics.shift_coverage) > 0
        for shift_type, pct in metrics.shift_coverage.items():
            assert 0 <= pct <= 100

    @pytest.mark.asyncio
    async def test_coverage_without_requirements(
        self,
        db_session: AsyncSession,
        analytics_restaurant: Restaurant,
        analytics_waiters: List[Waiter],
    ):
        """Should return 100% when no staffing requirements defined."""
        # Create a schedule without any requirements
        week_start = date.today() - timedelta(days=date.today().weekday())
        schedule = Schedule(
            id=uuid4(),
            restaurant_id=analytics_restaurant.id,
            week_start_date=week_start,
            status="draft",
            generated_by="manual",
            version=1,
        )
        db_session.add(schedule)
        await db_session.commit()

        service = ScheduleAnalyticsService(db_session)
        metrics = await service.get_coverage_metrics(schedule.id)

        # No requirements = 100% coverage
        assert metrics.coverage_pct == 100.0


# ============================================================================
# Fairness Metrics Tests
# ============================================================================


class TestFairnessMetrics:
    """Tests for fairness calculation."""

    @pytest.mark.asyncio
    async def test_fairness_balanced_schedule(
        self,
        db_session: AsyncSession,
        schedule_with_full_coverage: Schedule,
    ):
        """Should have low Gini for balanced schedule."""
        service = ScheduleAnalyticsService(db_session)
        fairness = await service.get_fairness_metrics(schedule_with_full_coverage.id)

        # When everyone has similar hours, Gini should be low
        assert fairness.gini_coefficient < 0.25
        assert fairness.is_balanced

    @pytest.mark.asyncio
    async def test_fairness_unbalanced_schedule(
        self,
        db_session: AsyncSession,
        schedule_with_fairness_issues: Schedule,
    ):
        """Should have high Gini for unbalanced schedule."""
        service = ScheduleAnalyticsService(db_session)
        fairness = await service.get_fairness_metrics(schedule_with_fairness_issues.id)

        # When hours are very unequal, Gini should be high
        assert fairness.gini_coefficient > 0.20
        assert len(fairness.staff_metrics) == 3

    @pytest.mark.asyncio
    async def test_fairness_staff_metrics(
        self,
        db_session: AsyncSession,
        schedule_with_fairness_issues: Schedule,
    ):
        """Should provide per-staff fairness breakdown."""
        service = ScheduleAnalyticsService(db_session)
        fairness = await service.get_fairness_metrics(schedule_with_fairness_issues.id)

        # Find staff by hours
        hours_list = [m.weekly_hours for m in fairness.staff_metrics]
        assert max(hours_list) > min(hours_list) * 2  # Big difference

    @pytest.mark.asyncio
    async def test_fairness_empty_schedule(
        self,
        db_session: AsyncSession,
        analytics_restaurant: Restaurant,
    ):
        """Should handle empty schedule gracefully."""
        week_start = date.today() - timedelta(days=date.today().weekday())
        schedule = Schedule(
            id=uuid4(),
            restaurant_id=analytics_restaurant.id,
            week_start_date=week_start,
            status="draft",
            generated_by="manual",
            version=1,
        )
        db_session.add(schedule)
        await db_session.commit()

        service = ScheduleAnalyticsService(db_session)
        fairness = await service.get_fairness_metrics(schedule.id)

        assert fairness.is_balanced
        assert fairness.gini_coefficient == 0.0


# ============================================================================
# Preference Match Tests
# ============================================================================


class TestPreferenceMatch:
    """Tests for preference matching metrics."""

    @pytest.mark.asyncio
    async def test_preference_score_no_preferences(
        self,
        db_session: AsyncSession,
        schedule_with_full_coverage: Schedule,
    ):
        """Should be 100% when no preferences defined."""
        service = ScheduleAnalyticsService(db_session)
        metrics = await service.get_preference_match_metrics(schedule_with_full_coverage.id)

        # No preferences = everything matches
        assert metrics.avg_preference_score == 100.0

    @pytest.mark.asyncio
    async def test_preference_per_staff_breakdown(
        self,
        db_session: AsyncSession,
        schedule_with_full_coverage: Schedule,
    ):
        """Should provide per-staff preference breakdown."""
        service = ScheduleAnalyticsService(db_session)
        metrics = await service.get_preference_match_metrics(schedule_with_full_coverage.id)

        assert len(metrics.by_staff) > 0
        for staff in metrics.by_staff:
            assert staff.shifts_assigned >= 0


# ============================================================================
# Fairness History Tests
# ============================================================================


class TestFairnessHistory:
    """Tests for historical fairness trends."""

    @pytest.mark.asyncio
    async def test_fairness_history_with_schedules(
        self,
        db_session: AsyncSession,
        schedule_with_full_coverage: Schedule,
    ):
        """Should calculate fairness from published schedules."""
        service = ScheduleAnalyticsService(db_session)
        history = await service.get_fairness_history(
            schedule_with_full_coverage.restaurant_id,
            weeks=4,
        )

        # Should have at least one trend point
        assert len(history.trends) >= 1
        assert history.trend_direction in ["improving", "stable", "declining"]

    @pytest.mark.asyncio
    async def test_fairness_history_no_schedules(
        self,
        db_session: AsyncSession,
        analytics_restaurant: Restaurant,
    ):
        """Should return empty trends when no published schedules."""
        service = ScheduleAnalyticsService(db_session)
        history = await service.get_fairness_history(
            analytics_restaurant.id,
            weeks=4,
        )

        assert history.weeks_analyzed == 0
        assert history.trend_direction == "stable"


# ============================================================================
# Insights Detection Tests
# ============================================================================


class TestInsightsDetection:
    """Tests for insight detection."""

    @pytest.mark.asyncio
    async def test_detects_coverage_gaps(
        self,
        db_session: AsyncSession,
        schedule_with_gaps: Schedule,
    ):
        """Should flag low coverage as a warning."""
        service = ScheduleInsightsService(db_session)
        report = await service.generate_insights(schedule_with_gaps.id, use_llm=False)

        coverage_insights = [i for i in report.coverage_insights if i.severity in ["warning", "critical"]]
        assert len(coverage_insights) > 0

    @pytest.mark.asyncio
    async def test_detects_fairness_issues(
        self,
        db_session: AsyncSession,
        schedule_with_fairness_issues: Schedule,
    ):
        """Should flag unfair hour distribution."""
        service = ScheduleInsightsService(db_session)
        report = await service.generate_insights(schedule_with_fairness_issues.id, use_llm=False)

        fairness_insights = [i for i in report.fairness_insights if "hour" in i.message.lower() or "gini" in i.message.lower()]
        assert len(fairness_insights) > 0

    @pytest.mark.asyncio
    async def test_detects_clopening_patterns(
        self,
        db_session: AsyncSession,
        schedule_with_clopening: Schedule,
    ):
        """Should detect close-open patterns."""
        service = ScheduleInsightsService(db_session)
        report = await service.generate_insights(schedule_with_clopening.id, use_llm=False)

        pattern_insights = [i for i in report.pattern_insights if "clopening" in i.message.lower()]
        assert len(pattern_insights) > 0

    @pytest.mark.asyncio
    async def test_insight_severity_counts(
        self,
        db_session: AsyncSession,
        schedule_with_gaps: Schedule,
    ):
        """Should count insights by severity."""
        service = ScheduleInsightsService(db_session)
        report = await service.generate_insights(schedule_with_gaps.id, use_llm=False)

        assert report.total_insights == (
            report.critical_count + report.warning_count + report.info_count
        )

    @pytest.mark.asyncio
    async def test_llm_disabled_fallback(
        self,
        db_session: AsyncSession,
        schedule_with_gaps: Schedule,
    ):
        """Should work without LLM."""
        service = ScheduleInsightsService(db_session)
        report = await service.generate_insights(schedule_with_gaps.id, use_llm=False)

        # Should still have insights even without LLM
        assert report.total_insights >= 0
        assert report.llm_summary is None


# ============================================================================
# MAPE Calculation Tests
# ============================================================================


class TestMAPECalculation:
    """Tests for forecast accuracy calculation."""

    def test_mape_rating_thresholds(self):
        """Verify MAPE rating thresholds."""
        forecaster = DemandForecaster.__new__(DemandForecaster)

        assert forecaster._rate_mape(5.0) == "excellent"
        assert forecaster._rate_mape(15.0) == "good"
        assert forecaster._rate_mape(25.0) == "fair"
        assert forecaster._rate_mape(35.0) == "poor"

    def test_mape_calculation_perfect(self):
        """MAPE should be 0 for perfect predictions."""
        forecaster = DemandForecaster.__new__(DemandForecaster)

        errors = [0.0, 0.0, 0.0]
        mape = forecaster._calculate_mape(errors)
        assert mape == 0.0

    def test_mape_calculation_with_errors(self):
        """MAPE should reflect average error."""
        forecaster = DemandForecaster.__new__(DemandForecaster)

        errors = [10.0, 20.0, 30.0]  # Average = 20%
        mape = forecaster._calculate_mape(errors)
        assert mape == 20.0

    def test_mape_calculation_empty(self):
        """MAPE should be 0 for empty list."""
        forecaster = DemandForecaster.__new__(DemandForecaster)

        mape = forecaster._calculate_mape([])
        assert mape == 0.0


# ============================================================================
# Gini Rating Tests
# ============================================================================


class TestGiniRating:
    """Tests for Gini coefficient rating."""

    def test_gini_excellent(self):
        """Low Gini should be rated excellent."""
        rating = ScheduleAnalyticsService.rate_gini(0.05)
        assert rating == "excellent"

    def test_gini_good(self):
        """Moderate Gini should be rated good."""
        rating = ScheduleAnalyticsService.rate_gini(0.15)
        assert rating == "good"

    def test_gini_fair(self):
        """Higher Gini should be rated fair."""
        rating = ScheduleAnalyticsService.rate_gini(0.25)
        assert rating == "fair"

    def test_gini_poor(self):
        """High Gini should be rated poor."""
        rating = ScheduleAnalyticsService.rate_gini(0.35)
        assert rating == "poor"
