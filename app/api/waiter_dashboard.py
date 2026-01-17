"""
REST API endpoints for waiter dashboard and tier management.
"""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.dashboard_service import DashboardService
from app.services.tier_job import TierRecalculationJob
from app.services.seed_service import SeedService
from app.schemas.insights import (
    WaiterStatsResponse,
    TrendDataPoint,
    WaiterInsightsResponse,
    RecentShiftResponse,
    WaiterDashboardResponse,
    TierRecalculationRequest,
    TierRecalculationResponse,
    DemoSeedResponse,
    WaiterSummary,
)

router = APIRouter(prefix="/api/v1", tags=["waiter-dashboard"])
logger = logging.getLogger(__name__)


# ============================================================================
# Separate Endpoints
# ============================================================================

@router.get("/waiters/{waiter_id}/stats", response_model=WaiterStatsResponse)
async def get_waiter_stats(
    waiter_id: UUID,
    period: str = Query("month", description="Period: month, week, or day"),
    session: AsyncSession = Depends(get_session),
) -> WaiterStatsResponse:
    """
    Get stats for a waiter for a given period.

    - **period**: "month", "week", or "day"

    Returns covers, tips, avg/cover, and efficiency metrics.
    """
    service = DashboardService(session)
    stats = await service.get_waiter_stats(waiter_id, period=period)
    logger.info("Waiter stats response", extra={"waiter_id": str(waiter_id), "period": period, "stats": stats.model_dump()})
    return stats


@router.get("/waiters/{waiter_id}/trends", response_model=List[TrendDataPoint])
async def get_waiter_trends(
    waiter_id: UUID,
    months: int = Query(6, ge=1, le=12, description="Number of months"),
    session: AsyncSession = Depends(get_session),
) -> List[TrendDataPoint]:
    """
    Get monthly trend data for a waiter.

    Returns data for rendering a trend chart (tips, covers per month).
    """
    service = DashboardService(session)
    return await service.get_waiter_trends(waiter_id, months=months)


@router.get("/waiters/{waiter_id}/insights", response_model=Optional[WaiterInsightsResponse])
async def get_waiter_insights(
    waiter_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> Optional[WaiterInsightsResponse]:
    """
    Get LLM-generated insights for a waiter.

    Returns strengths, areas to watch, suggestions, and summary.
    These are cached from the weekly tier recalculation job.
    """
    service = DashboardService(session)
    return await service.get_waiter_insights(waiter_id)


@router.get("/waiters/{waiter_id}/shifts", response_model=List[RecentShiftResponse])
async def get_waiter_shifts(
    waiter_id: UUID,
    limit: int = Query(10, ge=1, le=50, description="Max shifts to return"),
    session: AsyncSession = Depends(get_session),
) -> List[RecentShiftResponse]:
    """
    Get recent shifts for a waiter.

    Returns shift history with hours, covers, tips, and efficiency.
    """
    service = DashboardService(session)
    return await service.get_recent_shifts(waiter_id, limit=limit)


# ============================================================================
# Unified Dashboard Endpoint
# ============================================================================

@router.get("/waiters/{waiter_id}/dashboard", response_model=WaiterDashboardResponse)
async def get_waiter_dashboard(
    waiter_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> WaiterDashboardResponse:
    """
    Get complete dashboard data for a waiter.

    Returns all dashboard components in one response:
    - Profile info (name, tier, tenure)
    - This month stats
    - 6-month trend
    - LLM insights
    - Recent shifts
    """
    service = DashboardService(session)
    dashboard = await service.get_waiter_dashboard(waiter_id)

    if dashboard is None:
        raise HTTPException(status_code=404, detail="Waiter not found")

    logger.info("Waiter dashboard response", extra={"waiter_id": str(waiter_id), "dashboard": dashboard.model_dump()})
    return dashboard


# ============================================================================
# Tier Recalculation Endpoints
# ============================================================================

@router.post(
    "/restaurants/{restaurant_id}/recalculate-tiers",
    response_model=TierRecalculationResponse,
)
async def recalculate_restaurant_tiers(
    restaurant_id: UUID,
    request: TierRecalculationRequest = TierRecalculationRequest(),
    background_tasks: BackgroundTasks = None,
    session: AsyncSession = Depends(get_session),
) -> TierRecalculationResponse:
    """
    Trigger tier recalculation for all waiters in a restaurant.

    This is typically run weekly via cron, but can be triggered manually.

    - **force**: Force recalculation even if recent insights exist
    - **waiter_ids**: Optional list of specific waiters to recalculate

    Note: LLM scoring requires the call_llm function to be configured.
    """
    job = TierRecalculationJob(
        session=session,
        call_llm_func=None,  # Will use fallback scoring
    )

    result = await job.run(
        restaurant_id=restaurant_id,
        use_llm=True,
    )

    return TierRecalculationResponse(
        success=result.success,
        message=f"Processed {result.waiters_processed} waiters",
        waiters_processed=result.waiters_processed,
        errors=result.errors,
    )


@router.post(
    "/waiters/{waiter_id}/recalculate-tier",
    response_model=TierRecalculationResponse,
)
async def recalculate_waiter_tier(
    waiter_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> TierRecalculationResponse:
    """
    Recalculate tier for a single waiter.

    Useful for on-demand refresh after significant performance changes.
    """
    job = TierRecalculationJob(
        session=session,
        call_llm_func=None,  # Will use fallback scoring
    )

    result = await job.run_for_waiter(
        waiter_id=waiter_id,
        use_llm=True,
    )

    if not result.success:
        raise HTTPException(
            status_code=400,
            detail=result.errors[0] if result.errors else "Recalculation failed",
        )

    return TierRecalculationResponse(
        success=result.success,
        message="Tier recalculated successfully",
        waiters_processed=result.waiters_processed,
        errors=result.errors,
    )


# ============================================================================
# Seed/Cold Start Endpoints
# ============================================================================

@router.post("/seed/default-data")
async def seed_default_data(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Seed default data for cold start.

    Creates a default restaurant with sections, tables, and waiters
    if no data exists. Safe to call multiple times.
    """
    service = SeedService(session)
    return await service.ensure_default_data()


@router.post("/restaurants/{restaurant_id}/seed/sample-data")
async def seed_sample_data(
    restaurant_id: UUID,
    days_back: int = Query(30, ge=1, le=90, description="Days of history"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Create sample shifts and visits for development/demo.

    Creates random but realistic historical data for testing
    the dashboard and analytics features.
    """
    service = SeedService(session)
    return await service.create_sample_shifts_and_visits(
        restaurant_id=restaurant_id,
        days_back=days_back,
    )


@router.post("/seed/demo", response_model=DemoSeedResponse)
async def seed_demo(
    days_back: int = Query(30, ge=1, le=90, description="Days of sample history to create"),
    run_tiers: bool = Query(True, description="Run tier calculation after seeding"),
    session: AsyncSession = Depends(get_session),
) -> DemoSeedResponse:
    """
    **One-stop demo seeding for frontend development.**

    This endpoint does everything needed to get a working demo in a single call:

    1. Creates a default restaurant if none exists (or uses existing one)
    2. Creates 4 sample waiters with different tiers
    3. Creates sections (Main Floor, Patio, Bar) and tables
    4. Creates sample shifts and visits for the past N days
    5. Runs tier calculation to populate insights and scores

    **Usage:**
    ```bash
    # Just POST to get everything set up
    curl -X POST http://localhost:8000/api/v1/seed/demo

    # Then use any waiter_id from the response to fetch their dashboard
    curl http://localhost:8000/api/v1/waiters/{waiter_id}/dashboard
    ```

    **Response includes:**
    - `restaurant_id`: The restaurant UUID
    - `waiters`: List of waiter IDs with their names and tiers
    - `dashboard_url_template`: URL template for fetching dashboards

    **Idempotent:** Safe to call multiple times. If data already exists,
    it will use the existing restaurant and skip sample data creation.
    """
    service = SeedService(session)
    result = await service.seed_demo(
        days_back=days_back,
        run_tier_calculation=run_tiers,
    )

    return DemoSeedResponse(
        success=result["success"],
        message=result["message"],
        restaurant_id=result["restaurant_id"],
        restaurant_name=result["restaurant_name"],
        waiters=[
            WaiterSummary(
                id=w["id"],
                name=w["name"],
                tier=w["tier"],
                composite_score=w["composite_score"],
            )
            for w in result["waiters"]
        ],
        shifts_created=result["shifts_created"],
        visits_created=result["visits_created"],
        days_of_history=result["days_of_history"],
        tiers_calculated=result["tiers_calculated"],
    )
