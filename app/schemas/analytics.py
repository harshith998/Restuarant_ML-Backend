"""Schemas for schedule analytics and insights."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Coverage Metrics Schemas
# ============================================================================


class DailyCoverageResponse(BaseModel):
    """Coverage metrics for a single day."""

    date: date
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday, 6=Sunday")
    day_name: str = Field(..., description="Day name (e.g., Monday)")
    slots_required: int = Field(..., ge=0)
    slots_filled: int = Field(..., ge=0)
    coverage_pct: float = Field(..., ge=0, le=100)


class UnderstaffedSlotResponse(BaseModel):
    """A time slot that didn't meet staffing requirements."""

    date: date
    day_name: str
    start_time: time
    end_time: time
    role: str
    required: int = Field(..., ge=1)
    filled: int = Field(..., ge=0)
    shortfall: int = Field(..., ge=1)


class CoverageMetricsResponse(BaseModel):
    """Response for schedule coverage metrics."""

    schedule_id: UUID
    week_start: date
    total_slots_required: int = Field(..., ge=0)
    total_slots_filled: int = Field(..., ge=0)
    coverage_pct: float = Field(..., ge=0, le=100)
    daily_coverage: List[DailyCoverageResponse] = Field(default_factory=list)
    shift_coverage: Dict[str, float] = Field(
        default_factory=dict,
        description="Coverage by shift type (morning, afternoon, evening)"
    )
    understaffed_slots: List[UnderstaffedSlotResponse] = Field(default_factory=list)


# ============================================================================
# Fairness Metrics Schemas
# ============================================================================


class StaffFairnessResponse(BaseModel):
    """Fairness metrics for a single staff member."""

    waiter_id: UUID
    name: str
    weekly_hours: float = Field(..., ge=0)
    hours_vs_target: float = Field(..., description="Hours difference from target (+/-)")
    prime_shifts_count: int = Field(..., ge=0)
    fairness_score: float = Field(..., ge=0, le=100)


class FairnessMetricsResponse(BaseModel):
    """Response for schedule fairness metrics."""

    schedule_id: UUID
    week_start: date
    gini_coefficient: float = Field(..., ge=0, le=1, description="0=equal, 1=unequal")
    gini_rating: str = Field(..., description="excellent/good/fair/poor")
    hours_std_dev: float = Field(..., ge=0)
    prime_shift_gini: float = Field(..., ge=0, le=1)
    is_balanced: bool
    fairness_issues: List[str] = Field(default_factory=list)
    staff_metrics: List[StaffFairnessResponse] = Field(default_factory=list)


# ============================================================================
# Preference Match Schemas
# ============================================================================


class StaffPreferenceMatchResponse(BaseModel):
    """Preference match details for a single staff member."""

    waiter_id: UUID
    name: str
    preference_score: float = Field(..., ge=0, le=100)
    role_matched: bool
    shift_type_matched: bool
    section_matched: bool
    shifts_assigned: int = Field(..., ge=0)


class PreferenceMetricsResponse(BaseModel):
    """Response for preference match metrics."""

    schedule_id: UUID
    avg_preference_score: float = Field(..., ge=0, le=100)
    role_match_pct: float = Field(..., ge=0, le=100)
    shift_type_match_pct: float = Field(..., ge=0, le=100)
    section_match_pct: float = Field(..., ge=0, le=100)
    by_staff: List[StaffPreferenceMatchResponse] = Field(default_factory=list)


# ============================================================================
# Forecast Accuracy Schemas
# ============================================================================


class DailyAccuracyResponse(BaseModel):
    """Forecast accuracy for a single day."""

    date: date
    day_name: str
    predicted_covers: float = Field(..., ge=0)
    actual_covers: int = Field(..., ge=0)
    absolute_error: float = Field(..., ge=0)
    percentage_error: float = Field(..., description="Absolute percentage error")


class ForecastAccuracyResponse(BaseModel):
    """Response for forecast vs actual comparison."""

    week_start: date
    restaurant_id: UUID
    mape: float = Field(..., ge=0, description="Mean Absolute Percentage Error")
    mape_rating: str = Field(..., description="excellent/good/fair/poor")
    total_predicted_covers: float = Field(..., ge=0)
    total_actual_covers: int = Field(..., ge=0)
    variance_pct: float = Field(..., description="Overall variance percentage")
    daily_accuracy: List[DailyAccuracyResponse] = Field(default_factory=list)


class WeekAccuracyResponse(BaseModel):
    """Brief accuracy summary for a single week."""

    week_start: date
    mape: float = Field(..., ge=0)
    mape_rating: str
    actual_covers: int = Field(..., ge=0)


class AccuracyTrendResponse(BaseModel):
    """Response for historical forecast accuracy trends."""

    restaurant_id: UUID
    weeks: List[WeekAccuracyResponse] = Field(default_factory=list)
    avg_mape: float = Field(..., ge=0)
    trend_direction: str = Field(..., description="improving/stable/declining")


# ============================================================================
# Fairness Trend Schemas
# ============================================================================


class FairnessTrendPointResponse(BaseModel):
    """Fairness metrics for a single week."""

    week_start: date
    gini_coefficient: float = Field(..., ge=0, le=1)
    hours_std_dev: float = Field(..., ge=0)
    prime_shift_gini: float = Field(..., ge=0, le=1)
    is_balanced: bool
    staff_count: int = Field(..., ge=0)


class FairnessTrendResponse(BaseModel):
    """Response for historical fairness trends."""

    restaurant_id: UUID
    trends: List[FairnessTrendPointResponse] = Field(default_factory=list)
    avg_gini: float = Field(..., ge=0, le=1)
    trend_direction: str = Field(..., description="improving/stable/declining")
    weeks_analyzed: int = Field(..., ge=0)


# ============================================================================
# Schedule Insights Schemas
# ============================================================================


class ScheduleInsightResponse(BaseModel):
    """Single insight about a schedule."""

    category: str = Field(..., description="coverage/fairness/pattern")
    severity: str = Field(..., description="info/warning/critical")
    message: str
    affected_staff_count: int = Field(0, ge=0)
    affected_staff_names: List[str] = Field(default_factory=list)
    metric_value: Optional[float] = None
    recommendation: Optional[str] = None


class ScheduleInsightsResponse(BaseModel):
    """Response for schedule insights."""

    schedule_id: UUID
    week_start: date
    generated_at: datetime
    total_insights: int = Field(..., ge=0)
    critical_count: int = Field(0, ge=0)
    warning_count: int = Field(0, ge=0)
    info_count: int = Field(0, ge=0)
    coverage_insights: List[ScheduleInsightResponse] = Field(default_factory=list)
    fairness_insights: List[ScheduleInsightResponse] = Field(default_factory=list)
    pattern_insights: List[ScheduleInsightResponse] = Field(default_factory=list)
    llm_summary: Optional[str] = None
    llm_model: Optional[str] = None


# ============================================================================
# Unified Schedule Performance Schema
# ============================================================================


class SchedulePerformanceResponse(BaseModel):
    """Unified schedule performance response combining all analytics."""

    schedule_id: UUID
    week_start: date
    status: str = Field(..., description="draft/published/archived")
    coverage: CoverageMetricsResponse
    fairness: FairnessMetricsResponse
    preferences: PreferenceMetricsResponse
    insights: ScheduleInsightsResponse


# ============================================================================
# Cache Model Schemas (for ScheduleInsights model)
# ============================================================================


class ScheduleInsightsRead(BaseModel):
    """Schema for reading cached schedule insights from database."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    schedule_id: UUID
    restaurant_id: UUID
    coverage_pct: Optional[float]
    gini_coefficient: Optional[float]
    avg_preference_score: Optional[float]
    critical_count: int
    warning_count: int
    info_count: int
    coverage_insights: List[dict] = Field(default_factory=list)
    fairness_insights: List[dict] = Field(default_factory=list)
    pattern_insights: List[dict] = Field(default_factory=list)
    llm_summary: Optional[str]
    llm_model: Optional[str]
    schedule_version: int
    generated_at: datetime
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Cold Start Response (empty state)
# ============================================================================


class ColdStartAnalyticsResponse(BaseModel):
    """Response when no analytics data is available (cold start)."""

    message: str = Field(
        default="No analytics data available yet",
        description="Explanation for empty state"
    )
    hint: str = Field(
        default="Create and publish a schedule to generate analytics",
        description="Guidance for the user"
    )
    schedule_id: Optional[UUID] = None
    has_schedules: bool = False
    has_published_schedules: bool = False
    has_visits: bool = False
