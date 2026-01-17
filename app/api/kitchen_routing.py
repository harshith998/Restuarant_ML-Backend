from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.kitchen_routing_service import KitchenRoutingService

router = APIRouter(prefix="/api/v1/kitchen", tags=["kitchen-routing"])


@router.post("/visits/{visit_id}/route")
async def route_visit_to_stations(
    visit_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """
    Route a visit's orders to appropriate kitchen stations.
    
    Returns station assignments with batch prep recommendations.
    """
    service = KitchenRoutingService(session)
    
    try:
        routing = await service.route_visit_to_stations(visit_id)
        return routing
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
