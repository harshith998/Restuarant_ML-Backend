from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.menu_optimization_service import MenuOptimizationService

router = APIRouter(prefix="/api/v1/restaurants/{restaurant_id}/menu", tags=["menu-analytics"])


@router.get("/pricing-recommendations")
async def get_pricing_recommendations(
    restaurant_id: UUID,
    lookback_days: int = 30,
    session: AsyncSession = Depends(get_session),
):
    """
    Get menu pricing optimization recommendations.
    
    Analyzes demand and profit margins to suggest price adjustments.
    """
    service = MenuOptimizationService(session)
    recommendations = await service.get_pricing_recommendations(restaurant_id, lookback_days)
    
    return {
        "restaurant_id": str(restaurant_id),
        "analysis_period_days": lookback_days,
        "total_recommendations": len(recommendations),
        "recommendations": recommendations,
    }


@router.get("/top-sellers")
async def get_top_sellers(
    restaurant_id: UUID,
    period_days: int = 7,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    """
    Get top selling menu items by revenue and order count.
    """
    service = MenuOptimizationService(session)
    top_sellers = await service.get_top_sellers(restaurant_id, period_days, limit)
    
    return {
        "restaurant_id": str(restaurant_id),
        "period_days": period_days,
        "top_sellers": top_sellers,
    }
