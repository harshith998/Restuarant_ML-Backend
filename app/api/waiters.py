"""
REST API endpoints for waiter management.
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.waiter import Waiter
from app.schemas.waiter import WaiterCreate, WaiterRead, WaiterUpdate, WaiterWithShiftStats
from app.services.waiter_service import WaiterService

router = APIRouter(prefix="/api/v1", tags=["waiters"])


@router.get("/restaurants/{restaurant_id}/waiters", response_model=List[WaiterRead])
async def list_waiters(
    restaurant_id: UUID,
    include_inactive: bool = Query(False, description="Include inactive waiters"),
    session: AsyncSession = Depends(get_session),
) -> List[WaiterRead]:
    """Get all waiters for a restaurant."""
    query = select(Waiter).where(Waiter.restaurant_id == restaurant_id)

    if not include_inactive:
        query = query.where(Waiter.is_active == True)

    query = query.order_by(Waiter.name)

    result = await session.execute(query)
    waiters = result.scalars().all()

    return [WaiterRead.model_validate(w) for w in waiters]


@router.get("/restaurants/{restaurant_id}/waiters/active")
async def get_active_waiters(
    restaurant_id: UUID,
    section_id: Optional[UUID] = Query(None, description="Filter by section"),
    session: AsyncSession = Depends(get_session),
) -> List[dict]:
    """
    Get waiters who are currently on shift with their stats.

    Includes current tables, tips, and covers for the shift.
    """
    service = WaiterService(session)

    section_ids = {section_id} if section_id else None

    waiters = await service.get_available_waiters(
        restaurant_id=restaurant_id,
        section_ids=section_ids,
    )

    return [
        {
            "id": str(w.id),
            "name": w.name,
            "tier": w.tier,
            "composite_score": float(w.composite_score),
            "current_tables": w.current_tables,
            "current_tips": float(w.current_tips),
            "current_covers": w.current_covers,
            "section_id": str(w.section_id) if w.section_id else None,
            "status": w.status,
        }
        for w in waiters
    ]


@router.get("/waiters/{waiter_id}", response_model=WaiterRead)
async def get_waiter(
    waiter_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> WaiterRead:
    """Get a waiter by ID."""
    result = await session.execute(
        select(Waiter).where(Waiter.id == waiter_id)
    )
    waiter = result.scalar_one_or_none()

    if waiter is None:
        raise HTTPException(status_code=404, detail="Waiter not found")

    return WaiterRead.model_validate(waiter)


@router.post("/restaurants/{restaurant_id}/waiters", response_model=WaiterRead)
async def create_waiter(
    restaurant_id: UUID,
    data: WaiterCreate,
    session: AsyncSession = Depends(get_session),
) -> WaiterRead:
    """Create a new waiter."""
    waiter = Waiter(
        restaurant_id=restaurant_id,
        name=data.name,
        email=data.email,
        phone=data.phone,
    )
    session.add(waiter)
    await session.commit()
    await session.refresh(waiter)

    return WaiterRead.model_validate(waiter)


@router.patch("/waiters/{waiter_id}", response_model=WaiterRead)
async def update_waiter(
    waiter_id: UUID,
    data: WaiterUpdate,
    session: AsyncSession = Depends(get_session),
) -> WaiterRead:
    """Update a waiter."""
    result = await session.execute(
        select(Waiter).where(Waiter.id == waiter_id)
    )
    waiter = result.scalar_one_or_none()

    if waiter is None:
        raise HTTPException(status_code=404, detail="Waiter not found")

    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(waiter, field, value)

    await session.commit()
    await session.refresh(waiter)

    return WaiterRead.model_validate(waiter)


@router.get("/restaurants/{restaurant_id}/waiters/leaderboard")
async def get_leaderboard(
    restaurant_id: UUID,
    limit: int = Query(10, le=50),
    session: AsyncSession = Depends(get_session),
) -> List[dict]:
    """
    Get waiter leaderboard by composite score.

    Returns top performers for the restaurant.
    """
    result = await session.execute(
        select(Waiter)
        .where(
            Waiter.restaurant_id == restaurant_id,
            Waiter.is_active == True,
        )
        .order_by(Waiter.composite_score.desc())
        .limit(limit)
    )
    waiters = result.scalars().all()

    return [
        {
            "rank": i + 1,
            "id": str(w.id),
            "name": w.name,
            "tier": w.tier,
            "composite_score": float(w.composite_score),
            "total_shifts": w.total_shifts,
            "total_covers": w.total_covers,
            "total_tips": float(w.total_tips),
        }
        for i, w in enumerate(waiters)
    ]
