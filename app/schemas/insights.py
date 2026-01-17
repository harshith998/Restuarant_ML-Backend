"""Schemas for waiter insights and dashboard data."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WaiterStatsResponse(BaseModel):
    """This month's stats for a waiter."""

    covers: int = Field(..., description="Total covers served")
    tips: float = Field(..., description="Total tips earned")
    avg_per_cover: float = Field(..., description="Average revenue per cover")
    efficiency_pct: float = Field(..., description="Efficiency percentage (0-100)")
    tables_served: int = Field(0, description="Total tables served")
    total_sales: float = Field(0, description="Total sales amount")


class TrendDataPoint(BaseModel):
    """Single data point for trend chart."""

    month: str = Field(..., description="Month in YYYY-MM format")
    tips: float = Field(..., description="Total tips for the month")
    covers: int = Field(..., description="Total covers for the month")
    avg_tip_pct: Optional[float] = Field(None, description="Average tip percentage")


class WaiterInsightsResponse(BaseModel):
    """LLM-generated insights for a waiter."""

    tier: str = Field(..., description="Current tier: strong/standard/developing")
    composite_score: float = Field(..., description="Overall score (0-100)")
    math_score: Optional[float] = Field(None, description="PRD formula score")
    llm_score: Optional[float] = Field(None, description="LLM-adjusted score")
    strengths: List[str] = Field(default_factory=list, description="List of strengths")
    areas_to_watch: List[str] = Field(default_factory=list, description="Areas needing improvement")
    suggestions: List[str] = Field(default_factory=list, description="Actionable suggestions")
    llm_summary: Optional[str] = Field(None, description="Full LLM analysis")
    computed_at: Optional[datetime] = Field(None, description="When insights were generated")
    llm_model: Optional[str] = Field(None, description="LLM model used")


class RecentShiftResponse(BaseModel):
    """Recent shift data for display."""

    id: UUID
    date: date
    clock_in: datetime
    clock_out: Optional[datetime] = None
    hours: str = Field(..., description="Formatted hours like '4-11pm'")
    covers: int
    tips: float
    sales: float
    efficiency_pct: float = Field(..., description="Efficiency percentage")
    section_name: Optional[str] = None


class WaiterProfileResponse(BaseModel):
    """Basic waiter profile info."""

    id: UUID
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    tier: str
    tenure_years: float = Field(..., description="Years since created_at")
    total_shifts: int
    total_covers: int
    total_tips: float
    is_active: bool
    created_at: datetime


class WaiterProfileForDashboard(BaseModel):
    """Waiter profile for dashboard response."""

    id: UUID
    name: str
    tier: str
    tenure_years: float
    email: Optional[str] = None
    phone: Optional[str] = None
    total_shifts: int = 0
    total_covers: int = 0
    total_tips: float = 0.0
    is_active: bool = True
    created_at: datetime


class WaiterDashboardResponse(BaseModel):
    """Unified dashboard response with all waiter data."""

    model_config = ConfigDict(from_attributes=True)

    # Profile wrapped in object
    profile: WaiterProfileForDashboard

    # Lifetime stats (aggregated)
    stats: WaiterStatsResponse

    # 6-month trend
    trends: List[TrendDataPoint]

    # LLM insights
    insights: Optional[WaiterInsightsResponse] = None

    # Recent shifts
    recent_shifts: List[RecentShiftResponse]


class WaiterInsightsCreate(BaseModel):
    """Schema for creating waiter insights."""

    waiter_id: UUID
    restaurant_id: UUID
    math_score: Optional[float] = None
    llm_score: Optional[float] = None
    composite_score: Optional[float] = None
    tier: Optional[str] = None
    turn_time_zscore: Optional[float] = None
    tip_pct_zscore: Optional[float] = None
    covers_zscore: Optional[float] = None
    strengths: List[str] = Field(default_factory=list)
    areas_to_watch: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    llm_summary: Optional[str] = None
    monthly_trends: dict = Field(default_factory=dict)
    metrics_snapshot: dict = Field(default_factory=dict)
    period_start: date
    period_end: Optional[date] = None
    llm_model: Optional[str] = None


class WaiterInsightsRead(BaseModel):
    """Schema for reading waiter insights."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    waiter_id: UUID
    restaurant_id: UUID
    math_score: Optional[float]
    llm_score: Optional[float]
    composite_score: Optional[float]
    tier: Optional[str]
    turn_time_zscore: Optional[float]
    tip_pct_zscore: Optional[float]
    covers_zscore: Optional[float]
    strengths: List[str]
    areas_to_watch: List[str]
    suggestions: List[str]
    llm_summary: Optional[str]
    monthly_trends: dict
    metrics_snapshot: dict
    period_start: date
    period_end: Optional[date]
    computed_at: datetime
    llm_model: Optional[str]


class TierRecalculationRequest(BaseModel):
    """Request to trigger tier recalculation."""

    force: bool = Field(False, description="Force recalculation even if recent insights exist")
    waiter_ids: Optional[List[UUID]] = Field(None, description="Specific waiters to recalculate")


class TierRecalculationResponse(BaseModel):
    """Response from tier recalculation."""

    success: bool
    message: str
    waiters_processed: int = 0
    errors: List[str] = Field(default_factory=list)


class WaiterSummary(BaseModel):
    """Brief waiter info for demo seed response."""

    id: UUID
    name: str
    tier: str
    composite_score: float


class DemoSeedResponse(BaseModel):
    """
    Response from the demo seed endpoint.

    Contains all the IDs and info the frontend needs to immediately
    start using the dashboard without any prior setup.
    """

    success: bool
    message: str

    # The restaurant that was created/used
    restaurant_id: UUID
    restaurant_name: str

    # List of waiters with their IDs for dashboard calls
    waiters: List[WaiterSummary]

    # Helpful URLs for the frontend
    dashboard_url_template: str = Field(
        default="/api/v1/waiters/{waiter_id}/dashboard",
        description="URL template for fetching waiter dashboard",
    )

    # Stats about what was seeded
    shifts_created: int = 0
    visits_created: int = 0
    days_of_history: int = 30
    tiers_calculated: bool = False

    # Hint for frontend
    hint: str = Field(
        default="Use any waiter_id from the 'waiters' list to call the dashboard endpoint",
        description="Usage hint for frontend developers",
    )
