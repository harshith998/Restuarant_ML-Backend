from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.menu_optimization_service import MenuOptimizationService
from app.services.menu_service import MenuService
from app.schemas.menu import (
    MenuItemRankingResponse,
    MenuItem86RecommendationResponse,
    MenuItem86Response,
    MenuItem86dListResponse,
)

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


# ============================================================
# Ranking Endpoints
# ============================================================


@router.get("/rankings/top", response_model=MenuItemRankingResponse)
async def get_top_ranked_items(
    restaurant_id: UUID,
    lookback_days: int = 30,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    """
    Get highest scoring menu items by combined demand + margin score.

    Score formula: (normalized_demand * 0.5) + (margin_pct * 0.5)
    - normalized_demand: orders/day scaled to 0-100 based on max
    - margin_pct: profit margin percentage

    Use this to identify your best performers.
    """
    service = MenuService(session)
    items = await service.get_ranked_items(
        restaurant_id=restaurant_id,
        lookback_days=lookback_days,
        order="desc",
        limit=limit,
    )

    return MenuItemRankingResponse(
        restaurant_id=str(restaurant_id),
        analysis_period_days=lookback_days,
        total_items=len(items),
        items=items,
    )


@router.get("/rankings/bottom", response_model=MenuItemRankingResponse)
async def get_bottom_ranked_items(
    restaurant_id: UUID,
    lookback_days: int = 30,
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    """
    Get lowest scoring menu items by combined demand + margin score.

    Use this to identify underperformers that may need attention or removal.
    """
    service = MenuService(session)
    items = await service.get_ranked_items(
        restaurant_id=restaurant_id,
        lookback_days=lookback_days,
        order="asc",
        limit=limit,
    )

    return MenuItemRankingResponse(
        restaurant_id=str(restaurant_id),
        analysis_period_days=lookback_days,
        total_items=len(items),
        items=items,
    )


# ============================================================
# 86 Management Endpoints
# ============================================================


@router.get("/86-recommendations", response_model=MenuItem86RecommendationResponse)
async def get_86_recommendations(
    restaurant_id: UUID,
    lookback_days: int = 30,
    score_threshold: float = 25.0,
    session: AsyncSession = Depends(get_session),
):
    """
    Get menu items recommended to 86 based on low performance scores.

    Returns currently available items scoring below the threshold.
    Does NOT automatically 86 items - just provides recommendations.

    Args:
        lookback_days: Analysis period for demand calculation
        score_threshold: Items below this score are recommended (default: 25)
    """
    service = MenuService(session)
    recommendations = await service.get_86_recommendations(
        restaurant_id=restaurant_id,
        lookback_days=lookback_days,
        score_threshold=score_threshold,
    )

    return MenuItem86RecommendationResponse(
        restaurant_id=str(restaurant_id),
        analysis_period_days=lookback_days,
        score_threshold=score_threshold,
        total_recommendations=len(recommendations),
        recommendations=recommendations,
    )


@router.post("/items/{item_id}/86", response_model=MenuItem86Response)
async def eighty_six_item(
    restaurant_id: UUID,
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """
    86 a menu item (mark as unavailable).

    The item will no longer appear in available menu listings.
    Use /items/{item_id}/un-86 to restore.
    """
    service = MenuService(session)
    item = await service.set_86_status(item_id, is_available=False)

    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    return MenuItem86Response(
        success=True,
        item_id=str(item.id),
        name=item.name,
        is_available=item.is_available,
        message=f"'{item.name}' has been 86'd",
    )


@router.post("/items/{item_id}/un-86", response_model=MenuItem86Response)
async def un_eighty_six_item(
    restaurant_id: UUID,
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """
    Un-86 a menu item (restore availability).

    Restores the item to available status so it appears in menus again.
    """
    service = MenuService(session)
    item = await service.set_86_status(item_id, is_available=True)

    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    return MenuItem86Response(
        success=True,
        item_id=str(item.id),
        name=item.name,
        is_available=item.is_available,
        message=f"'{item.name}' has been restored to available",
    )


@router.get("/items/86d", response_model=MenuItem86dListResponse)
async def get_86d_items(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """
    Get all currently 86'd (unavailable) items for a restaurant.

    Useful for tracking what's been taken off the menu.
    """
    service = MenuService(session)
    items = await service.get_86d_items(restaurant_id)

    return MenuItem86dListResponse(
        restaurant_id=str(restaurant_id),
        total_86d=len(items),
        items=items,
    )
