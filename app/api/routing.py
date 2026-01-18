"""
REST API endpoints for intelligent party routing.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.routing import RouteRequest, RouteResponse
from app.schemas.visit import VisitRead
from app.services.routing_service import RoutingService
from app.services.restaurant_resolver import resolve_restaurant_id

router = APIRouter(prefix="/api/v1", tags=["routing"])


@router.post("/restaurants/{restaurant_id}/routing/recommend", response_model=RouteResponse)
async def recommend_seating(
    restaurant_id: str,
    request: RouteRequest,
    session: AsyncSession = Depends(get_session),
) -> RouteResponse:
    """
    Get a table and waiter recommendation for a party.

    Does NOT seat the party - just returns the recommendation.
    Use POST /routing/seat to execute the seating.

    Args:
        restaurant_id: The restaurant UUID
        request: Party details and preferences

    Returns:
        RouteResponse with recommended table and waiter
    """
    try:
        resolved_restaurant_id = await resolve_restaurant_id(restaurant_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    service = RoutingService(session)

    result = await service.route_party(
        restaurant_id=resolved_restaurant_id,
        party_size=request.party_size,
        table_preference=request.table_preference,
        location_preference=request.location_preference,
        waitlist_id=request.waitlist_id,
    )

    return result


@router.post("/restaurants/{restaurant_id}/routing/seat", response_model=VisitRead)
async def seat_party(
    restaurant_id: str,
    table_id: UUID,
    waiter_id: UUID,
    party_size: int,
    waitlist_id: Optional[UUID] = None,
    session: AsyncSession = Depends(get_session),
) -> VisitRead:
    """
    Execute seating after route decision.

    Creates a Visit, marks table as occupied, updates shift stats.

    Args:
        restaurant_id: The restaurant UUID
        table_id: Selected table UUID
        waiter_id: Assigned waiter UUID
        party_size: Number of people in party
        waitlist_id: Optional waitlist entry UUID

    Returns:
        The created Visit record
    """
    try:
        resolved_restaurant_id = await resolve_restaurant_id(restaurant_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    service = RoutingService(session)

    try:
        visit = await service.seat_party(
            restaurant_id=resolved_restaurant_id,
            table_id=table_id,
            waiter_id=waiter_id,
            party_size=party_size,
            waitlist_id=waitlist_id,
        )
        return VisitRead.model_validate(visit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/restaurants/{restaurant_id}/routing/mode")
async def switch_routing_mode(
    restaurant_id: str,
    mode: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Switch routing mode for a restaurant.

    Args:
        restaurant_id: The restaurant UUID
        mode: New mode - 'section' or 'rotation'

    Returns:
        Confirmation with new mode
    """
    if mode not in ("section", "rotation"):
        raise HTTPException(
            status_code=400,
            detail="Mode must be 'section' or 'rotation'"
        )

    try:
        resolved_restaurant_id = await resolve_restaurant_id(restaurant_id, session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    service = RoutingService(session)

    try:
        await service.switch_mode(resolved_restaurant_id, mode)
        return {"status": "ok", "mode": mode}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
