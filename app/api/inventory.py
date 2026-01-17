from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.inventory_service import InventoryService

router = APIRouter(prefix="/api/v1/restaurants/{restaurant_id}/inventory", tags=["inventory"])


@router.get("/shopping-list")
async def get_shopping_list(
    restaurant_id: UUID,
    forecast_days: int = 7,
    lookback_days: int = 30,
    session: AsyncSession = Depends(get_session),
):
    """
    Generate shopping list based on historical usage and current stock.
    
    Returns ingredients to order with quantities and costs.
    """
    service = InventoryService(session)
    shopping_list = await service.generate_shopping_list(
        restaurant_id, forecast_days, lookback_days
    )
    
    return shopping_list


@router.get("/stock-alerts")
async def get_stock_alerts(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """
    Get ingredients currently below par level.
    """
    service = InventoryService(session)
    alerts = await service.get_stock_alerts(restaurant_id)
    
    return {
        "restaurant_id": str(restaurant_id),
        "total_alerts": len(alerts),
        "low_stock_items": alerts,
    }
