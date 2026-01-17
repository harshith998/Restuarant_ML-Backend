"""
REST API endpoints for schedule analytics and insights.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Schedule
from app.services.demand_forecaster import DemandForecaster
from app.services.schedule_analytics import ScheduleAnalyticsService
from app.services.schedule_insights import ScheduleInsightsService
from app.schemas.analytics import (
    CoverageMetricsResponse,
    DailyCoverageResponse,
    UnderstaffedSlotResponse,
    FairnessMetricsResponse,
    StaffFairnessResponse,
    PreferenceMetricsResponse,
    StaffPreferenceMatchResponse,
    ForecastAccuracyResponse,
    DailyAccuracyResponse,
    AccuracyTrendResponse,
    WeekAccuracyResponse,
    FairnessTrendResponse,
    FairnessTrendPointResponse,
    ScheduleInsightsResponse,
    ScheduleInsightResponse,
    SchedulePerformanceResponse,
    ColdStartAnalyticsResponse,
)

router = APIRouter(prefix="/api/v1", tags=["analytics"])

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ============================================================================
# Helper Functions
# ============================================================================


async def _validate_schedule_ownership(
    session: AsyncSession,
    restaurant_id: UUID,
    schedule_id: UUID,
) -> Schedule:
    """Validate that schedule belongs to restaurant."""
    stmt = select(Schedule).where(Schedule.id == schedule_id)
    result = await session.execute(stmt)
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if schedule.restaurant_id != restaurant_id:
        raise HTTPException(status_code=403, detail="Schedule does not belong to this restaurant")

    return schedule


# ============================================================================
# Schedule Performance Analytics
# ============================================================================


@router.get(
    "/restaurants/{restaurant_id}/analytics/schedule/{schedule_id}",
    response_model=SchedulePerformanceResponse,
    summary="Get unified schedule performance analytics",
)
async def get_schedule_performance(
    restaurant_id: UUID,
    schedule_id: UUID,
    use_llm: bool = Query(True, description="Use LLM for insights summary"),
    session: AsyncSession = Depends(get_session),
) -> SchedulePerformanceResponse:
    """
    Get comprehensive performance metrics for a schedule.

    Returns:
    - **Coverage metrics**: % filled, understaffing
    - **Fairness metrics**: Gini coefficient, hours distribution
    - **Preference match metrics**: by staff
    - **Insights**: LLM-enhanced observations

    The restaurant_id in the path is validated against the schedule's restaurant.
    """
    schedule = await _validate_schedule_ownership(session, restaurant_id, schedule_id)

    analytics = ScheduleAnalyticsService(session)
    insights_service = ScheduleInsightsService(session)

    # Gather all metrics
    coverage = await analytics.get_coverage_metrics(schedule_id)
    fairness = await analytics.get_fairness_metrics(schedule_id)
    preferences = await analytics.get_preference_match_metrics(schedule_id)
    insights = await insights_service.generate_insights(schedule_id, use_llm=use_llm)

    # Convert to response schemas
    coverage_response = CoverageMetricsResponse(
        schedule_id=coverage.schedule_id,
        week_start=coverage.week_start,
        total_slots_required=coverage.total_slots_required,
        total_slots_filled=coverage.total_slots_filled,
        coverage_pct=coverage.coverage_pct,
        daily_coverage=[
            DailyCoverageResponse(
                date=d.date,
                day_of_week=d.day_of_week,
                day_name=DAY_NAMES[d.day_of_week],
                slots_required=d.slots_required,
                slots_filled=d.slots_filled,
                coverage_pct=d.coverage_pct,
            )
            for d in coverage.daily_coverage
        ],
        shift_coverage=coverage.shift_coverage,
        understaffed_slots=[
            UnderstaffedSlotResponse(
                date=s.date,
                day_name=DAY_NAMES[s.day_of_week],
                start_time=s.start_time,
                end_time=s.end_time,
                role=s.role,
                required=s.required,
                filled=s.filled,
                shortfall=s.shortfall,
            )
            for s in coverage.understaffed_slots
        ],
    )

    fairness_response = FairnessMetricsResponse(
        schedule_id=schedule_id,
        week_start=schedule.week_start_date,
        gini_coefficient=fairness.gini_coefficient,
        gini_rating=ScheduleAnalyticsService.rate_gini(fairness.gini_coefficient),
        hours_std_dev=fairness.hours_std_dev,
        prime_shift_gini=fairness.prime_shift_gini,
        is_balanced=fairness.is_balanced,
        fairness_issues=fairness.fairness_issues,
        staff_metrics=[
            StaffFairnessResponse(
                waiter_id=m.waiter_id,
                name=m.name,
                weekly_hours=m.weekly_hours,
                hours_vs_target=m.hours_vs_target,
                prime_shifts_count=m.prime_shifts_count,
                fairness_score=m.fairness_score,
            )
            for m in fairness.staff_metrics
        ],
    )

    preferences_response = PreferenceMetricsResponse(
        schedule_id=preferences.schedule_id,
        avg_preference_score=preferences.avg_preference_score,
        role_match_pct=preferences.role_match_pct,
        shift_type_match_pct=preferences.shift_type_match_pct,
        section_match_pct=preferences.section_match_pct,
        by_staff=[
            StaffPreferenceMatchResponse(
                waiter_id=s.waiter_id,
                name=s.waiter_name,
                preference_score=s.preference_score,
                role_matched=s.role_matched,
                shift_type_matched=s.shift_type_matched,
                section_matched=s.section_matched,
                shifts_assigned=s.shifts_assigned,
            )
            for s in preferences.by_staff
        ],
    )

    insights_response = ScheduleInsightsResponse(
        schedule_id=insights.schedule_id,
        week_start=insights.week_start,
        generated_at=insights.generated_at,
        total_insights=insights.total_insights,
        critical_count=insights.critical_count,
        warning_count=insights.warning_count,
        info_count=insights.info_count,
        coverage_insights=[
            ScheduleInsightResponse(
                category=i.category,
                severity=i.severity,
                message=i.message,
                affected_staff_count=len(i.affected_staff),
                affected_staff_names=i.affected_staff_names,
                metric_value=i.metric_value,
                recommendation=i.recommendation,
            )
            for i in insights.coverage_insights
        ],
        fairness_insights=[
            ScheduleInsightResponse(
                category=i.category,
                severity=i.severity,
                message=i.message,
                affected_staff_count=len(i.affected_staff),
                affected_staff_names=i.affected_staff_names,
                metric_value=i.metric_value,
                recommendation=i.recommendation,
            )
            for i in insights.fairness_insights
        ],
        pattern_insights=[
            ScheduleInsightResponse(
                category=i.category,
                severity=i.severity,
                message=i.message,
                affected_staff_count=len(i.affected_staff),
                affected_staff_names=i.affected_staff_names,
                metric_value=i.metric_value,
                recommendation=i.recommendation,
            )
            for i in insights.pattern_insights
        ],
        llm_summary=insights.llm_summary,
        llm_model=insights.llm_model,
    )

    return SchedulePerformanceResponse(
        schedule_id=schedule_id,
        week_start=schedule.week_start_date,
        status=schedule.status,
        coverage=coverage_response,
        fairness=fairness_response,
        preferences=preferences_response,
        insights=insights_response,
    )


@router.get(
    "/restaurants/{restaurant_id}/analytics/schedule/{schedule_id}/coverage",
    response_model=CoverageMetricsResponse,
    summary="Get schedule coverage metrics",
)
async def get_schedule_coverage(
    restaurant_id: UUID,
    schedule_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> CoverageMetricsResponse:
    """
    Get coverage metrics for a schedule.

    Shows how well the schedule meets staffing requirements:
    - Overall coverage percentage
    - Daily breakdown
    - Understaffed slots with shortfall details
    """
    await _validate_schedule_ownership(session, restaurant_id, schedule_id)

    analytics = ScheduleAnalyticsService(session)
    coverage = await analytics.get_coverage_metrics(schedule_id)

    return CoverageMetricsResponse(
        schedule_id=coverage.schedule_id,
        week_start=coverage.week_start,
        total_slots_required=coverage.total_slots_required,
        total_slots_filled=coverage.total_slots_filled,
        coverage_pct=coverage.coverage_pct,
        daily_coverage=[
            DailyCoverageResponse(
                date=d.date,
                day_of_week=d.day_of_week,
                day_name=DAY_NAMES[d.day_of_week],
                slots_required=d.slots_required,
                slots_filled=d.slots_filled,
                coverage_pct=d.coverage_pct,
            )
            for d in coverage.daily_coverage
        ],
        shift_coverage=coverage.shift_coverage,
        understaffed_slots=[
            UnderstaffedSlotResponse(
                date=s.date,
                day_name=DAY_NAMES[s.day_of_week],
                start_time=s.start_time,
                end_time=s.end_time,
                role=s.role,
                required=s.required,
                filled=s.filled,
                shortfall=s.shortfall,
            )
            for s in coverage.understaffed_slots
        ],
    )


@router.get(
    "/restaurants/{restaurant_id}/analytics/schedule/{schedule_id}/fairness",
    response_model=FairnessMetricsResponse,
    summary="Get schedule fairness metrics",
)
async def get_schedule_fairness(
    restaurant_id: UUID,
    schedule_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> FairnessMetricsResponse:
    """
    Get fairness metrics for a schedule.

    Shows equity of hour distribution:
    - Gini coefficient (0 = perfect equity)
    - Hours standard deviation
    - Prime shift distribution
    - Per-staff fairness scores
    """
    schedule = await _validate_schedule_ownership(session, restaurant_id, schedule_id)

    analytics = ScheduleAnalyticsService(session)
    fairness = await analytics.get_fairness_metrics(schedule_id)

    return FairnessMetricsResponse(
        schedule_id=schedule_id,
        week_start=schedule.week_start_date,
        gini_coefficient=fairness.gini_coefficient,
        gini_rating=ScheduleAnalyticsService.rate_gini(fairness.gini_coefficient),
        hours_std_dev=fairness.hours_std_dev,
        prime_shift_gini=fairness.prime_shift_gini,
        is_balanced=fairness.is_balanced,
        fairness_issues=fairness.fairness_issues,
        staff_metrics=[
            StaffFairnessResponse(
                waiter_id=m.waiter_id,
                name=m.name,
                weekly_hours=m.weekly_hours,
                hours_vs_target=m.hours_vs_target,
                prime_shifts_count=m.prime_shifts_count,
                fairness_score=m.fairness_score,
            )
            for m in fairness.staff_metrics
        ],
    )


@router.get(
    "/restaurants/{restaurant_id}/analytics/schedule/{schedule_id}/preferences",
    response_model=PreferenceMetricsResponse,
    summary="Get schedule preference match metrics",
)
async def get_schedule_preferences(
    restaurant_id: UUID,
    schedule_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PreferenceMetricsResponse:
    """
    Get preference matching metrics for a schedule.

    Shows how well assignments match staff preferences:
    - Average preference score
    - Role/shift/section match percentages
    - Per-staff breakdown
    """
    await _validate_schedule_ownership(session, restaurant_id, schedule_id)

    analytics = ScheduleAnalyticsService(session)
    preferences = await analytics.get_preference_match_metrics(schedule_id)

    return PreferenceMetricsResponse(
        schedule_id=preferences.schedule_id,
        avg_preference_score=preferences.avg_preference_score,
        role_match_pct=preferences.role_match_pct,
        shift_type_match_pct=preferences.shift_type_match_pct,
        section_match_pct=preferences.section_match_pct,
        by_staff=[
            StaffPreferenceMatchResponse(
                waiter_id=s.waiter_id,
                name=s.waiter_name,
                preference_score=s.preference_score,
                role_matched=s.role_matched,
                shift_type_matched=s.shift_type_matched,
                section_matched=s.section_matched,
                shifts_assigned=s.shifts_assigned,
            )
            for s in preferences.by_staff
        ],
    )


@router.get(
    "/restaurants/{restaurant_id}/analytics/schedule/{schedule_id}/insights",
    response_model=ScheduleInsightsResponse,
    summary="Get LLM-enhanced schedule insights",
)
async def get_schedule_insights(
    restaurant_id: UUID,
    schedule_id: UUID,
    use_llm: bool = Query(True, description="Use LLM for summary generation"),
    force_refresh: bool = Query(False, description="Force regenerate insights"),
    session: AsyncSession = Depends(get_session),
) -> ScheduleInsightsResponse:
    """
    Get AI-generated insights about a schedule.

    Returns actionable observations:
    - Coverage gaps and recommendations
    - Fairness issues
    - Problematic patterns (clopening, etc.)
    - LLM-generated summary
    """
    schedule = await _validate_schedule_ownership(session, restaurant_id, schedule_id)

    insights_service = ScheduleInsightsService(session)
    insights = await insights_service.generate_insights(
        schedule_id,
        use_llm=use_llm,
        force_refresh=force_refresh,
    )

    return ScheduleInsightsResponse(
        schedule_id=insights.schedule_id,
        week_start=insights.week_start,
        generated_at=insights.generated_at,
        total_insights=insights.total_insights,
        critical_count=insights.critical_count,
        warning_count=insights.warning_count,
        info_count=insights.info_count,
        coverage_insights=[
            ScheduleInsightResponse(
                category=i.category,
                severity=i.severity,
                message=i.message,
                affected_staff_count=len(i.affected_staff),
                affected_staff_names=i.affected_staff_names,
                metric_value=i.metric_value,
                recommendation=i.recommendation,
            )
            for i in insights.coverage_insights
        ],
        fairness_insights=[
            ScheduleInsightResponse(
                category=i.category,
                severity=i.severity,
                message=i.message,
                affected_staff_count=len(i.affected_staff),
                affected_staff_names=i.affected_staff_names,
                metric_value=i.metric_value,
                recommendation=i.recommendation,
            )
            for i in insights.fairness_insights
        ],
        pattern_insights=[
            ScheduleInsightResponse(
                category=i.category,
                severity=i.severity,
                message=i.message,
                affected_staff_count=len(i.affected_staff),
                affected_staff_names=i.affected_staff_names,
                metric_value=i.metric_value,
                recommendation=i.recommendation,
            )
            for i in insights.pattern_insights
        ],
        llm_summary=insights.llm_summary,
        llm_model=insights.llm_model,
    )


# ============================================================================
# Forecasting Analytics
# ============================================================================


@router.get(
    "/restaurants/{restaurant_id}/analytics/forecasting",
    response_model=ForecastAccuracyResponse,
    summary="Get forecast accuracy for a week",
)
async def get_forecast_accuracy(
    restaurant_id: UUID,
    week_start: date = Query(..., description="Monday of the week to analyze"),
    session: AsyncSession = Depends(get_session),
) -> ForecastAccuracyResponse:
    """
    Compare forecast predictions to actual covers for a past week.

    Returns:
    - **MAPE**: Mean Absolute Percentage Error
    - **Rating**: excellent/good/fair/poor
    - **Daily breakdown**: predicted vs actual per day

    Note: Can only analyze weeks that have already passed.
    """
    # Validate week_start is a Monday
    if week_start.weekday() != 0:
        raise HTTPException(
            status_code=400,
            detail="week_start must be a Monday"
        )

    # Validate week is in the past
    if week_start >= date.today():
        raise HTTPException(
            status_code=400,
            detail="Can only analyze completed weeks"
        )

    forecaster = DemandForecaster(session)
    accuracy = await forecaster.compare_forecast_to_actual(restaurant_id, week_start)

    return ForecastAccuracyResponse(
        week_start=accuracy.week_start,
        restaurant_id=accuracy.restaurant_id,
        mape=accuracy.mape,
        mape_rating=accuracy.mape_rating,
        total_predicted_covers=accuracy.total_predicted_covers,
        total_actual_covers=accuracy.total_actual_covers,
        variance_pct=accuracy.variance_pct,
        daily_accuracy=[
            DailyAccuracyResponse(
                date=d.date,
                day_name=DAY_NAMES[d.date.weekday()],
                predicted_covers=d.predicted_covers,
                actual_covers=d.actual_covers,
                absolute_error=d.absolute_error,
                percentage_error=d.percentage_error,
            )
            for d in accuracy.daily_accuracy
        ],
    )


@router.get(
    "/restaurants/{restaurant_id}/analytics/forecasting/trends",
    response_model=AccuracyTrendResponse,
    summary="Get historical forecast accuracy trends",
)
async def get_forecast_accuracy_trends(
    restaurant_id: UUID,
    weeks: int = Query(8, ge=4, le=26, description="Weeks of history"),
    session: AsyncSession = Depends(get_session),
) -> AccuracyTrendResponse:
    """
    Get historical forecast accuracy trends.

    Shows how forecast accuracy has changed over time:
    - Weekly MAPE values
    - Average MAPE
    - Trend direction (improving/stable/declining)
    """
    forecaster = DemandForecaster(session)
    trend = await forecaster.get_accuracy_trends(restaurant_id, weeks)

    return AccuracyTrendResponse(
        restaurant_id=trend.restaurant_id,
        weeks=[
            WeekAccuracyResponse(
                week_start=w.week_start,
                mape=w.mape,
                mape_rating=w.mape_rating,
                actual_covers=w.total_actual_covers,
            )
            for w in trend.weeks
        ],
        avg_mape=trend.avg_mape,
        trend_direction=trend.trend_direction,
    )


# ============================================================================
# Fairness Trends
# ============================================================================


@router.get(
    "/restaurants/{restaurant_id}/analytics/fairness-trends",
    response_model=FairnessTrendResponse,
    summary="Get historical fairness trends",
)
async def get_fairness_trends(
    restaurant_id: UUID,
    weeks: int = Query(12, ge=4, le=52, description="Weeks of history"),
    session: AsyncSession = Depends(get_session),
) -> FairnessTrendResponse:
    """
    Get historical fairness metrics across published schedules.

    Shows how schedule fairness has changed over time:
    - Weekly Gini coefficients
    - Balance status per week
    - Trend direction (improving/stable/declining)
    """
    analytics = ScheduleAnalyticsService(session)
    history = await analytics.get_fairness_history(restaurant_id, weeks)

    return FairnessTrendResponse(
        restaurant_id=history.restaurant_id,
        trends=[
            FairnessTrendPointResponse(
                week_start=t.week_start,
                gini_coefficient=t.gini_coefficient,
                hours_std_dev=t.hours_std_dev,
                prime_shift_gini=t.prime_shift_gini,
                is_balanced=t.is_balanced,
                staff_count=t.staff_count,
            )
            for t in history.trends
        ],
        avg_gini=history.avg_gini,
        trend_direction=history.trend_direction,
        weeks_analyzed=history.weeks_analyzed,
    )
