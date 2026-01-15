"""
REST API endpoints for visit management.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models.visit import Visit
from app.models.table import Table
from app.schemas.visit import VisitCreate, VisitRead, VisitUpdate
from app.services.table_service import TableService

router = APIRouter(prefix="/api/v1", tags=["visits"])


@router.get("/restaurants/{restaurant_id}/visits", response_model=List[VisitRead])
async def list_visits(
    restaurant_id: UUID,
    active_only: bool = Query(True, description="Only show active (not cleared) visits"),
    table_id: Optional[UUID] = Query(None, description="Filter by table"),
    waiter_id: Optional[UUID] = Query(None, description="Filter by waiter"),
    session: AsyncSession = Depends(get_session),
) -> List[VisitRead]:
    """Get visits for a restaurant."""
    query = select(Visit).where(Visit.restaurant_id == restaurant_id)

    if active_only:
        query = query.where(Visit.cleared_at.is_(None))

    if table_id:
        query = query.where(Visit.table_id == table_id)

    if waiter_id:
        query = query.where(Visit.waiter_id == waiter_id)

    query = query.order_by(Visit.seated_at.desc())

    result = await session.execute(query)
    visits = result.scalars().all()

    return [VisitRead.model_validate(v) for v in visits]


@router.get("/visits/{visit_id}", response_model=VisitRead)
async def get_visit(
    visit_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> VisitRead:
    """Get a visit by ID."""
    result = await session.execute(
        select(Visit).where(Visit.id == visit_id)
    )
    visit = result.scalar_one_or_none()

    if visit is None:
        raise HTTPException(status_code=404, detail="Visit not found")

    return VisitRead.model_validate(visit)


@router.post("/visits", response_model=VisitRead)
async def create_visit(
    data: VisitCreate,
    session: AsyncSession = Depends(get_session),
) -> VisitRead:
    """
    Create a visit manually.

    Note: Prefer using POST /routing/seat which handles
    table state updates and shift stats automatically.
    """
    visit = Visit(
        restaurant_id=data.restaurant_id,
        table_id=data.table_id,
        waiter_id=data.waiter_id,
        shift_id=data.shift_id,
        waitlist_id=data.waitlist_id,
        party_size=data.party_size,
        seated_at=data.seated_at or datetime.utcnow(),
    )
    session.add(visit)

    # Update table state
    table_service = TableService(session)
    await table_service.seat_table(data.table_id, visit.id)

    await session.commit()
    await session.refresh(visit)

    return VisitRead.model_validate(visit)


@router.patch("/visits/{visit_id}", response_model=VisitRead)
async def update_visit(
    visit_id: UUID,
    data: VisitUpdate,
    session: AsyncSession = Depends(get_session),
) -> VisitRead:
    """
    Update visit (payment info, timing, etc).
    """
    result = await session.execute(
        select(Visit).where(Visit.id == visit_id)
    )
    visit = result.scalar_one_or_none()

    if visit is None:
        raise HTTPException(status_code=404, detail="Visit not found")

    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)

    # Calculate tip percentage if tip and total provided
    if "tip" in update_data and "total" in update_data:
        total = update_data["total"]
        tip = update_data["tip"]
        if total and total > 0:
            update_data["tip_percentage"] = round((tip / total) * 100, 2)

    # Calculate duration if cleared_at set
    if "cleared_at" in update_data and update_data["cleared_at"]:
        duration = (update_data["cleared_at"] - visit.seated_at).total_seconds() / 60
        update_data["duration_minutes"] = int(duration)

    for field, value in update_data.items():
        setattr(visit, field, value)

    await session.commit()
    await session.refresh(visit)

    return VisitRead.model_validate(visit)


@router.post("/visits/{visit_id}/payment", response_model=VisitRead)
async def record_payment(
    visit_id: UUID,
    subtotal: float,
    tax: float,
    total: float,
    tip: float,
    pos_transaction_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
) -> VisitRead:
    """
    Record payment for a visit.

    Updates subtotal, tax, total, tip, and calculates tip percentage.
    """
    result = await session.execute(
        select(Visit).where(Visit.id == visit_id)
    )
    visit = result.scalar_one_or_none()

    if visit is None:
        raise HTTPException(status_code=404, detail="Visit not found")

    visit.subtotal = subtotal
    visit.tax = tax
    visit.total = total
    visit.tip = tip
    visit.payment_at = datetime.utcnow()

    if total > 0:
        visit.tip_percentage = round((tip / total) * 100, 2)

    if pos_transaction_id:
        visit.pos_transaction_id = pos_transaction_id

    await session.commit()
    await session.refresh(visit)

    return VisitRead.model_validate(visit)


@router.post("/visits/{visit_id}/clear", response_model=VisitRead)
async def clear_visit(
    visit_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> VisitRead:
    """
    Mark visit as cleared (party left, table now dirty).

    Sets cleared_at, calculates duration, and marks table as dirty.
    """
    result = await session.execute(
        select(Visit).where(Visit.id == visit_id)
    )
    visit = result.scalar_one_or_none()

    if visit is None:
        raise HTTPException(status_code=404, detail="Visit not found")

    if visit.cleared_at:
        raise HTTPException(status_code=400, detail="Visit already cleared")

    now = datetime.utcnow()
    visit.cleared_at = now
    visit.duration_minutes = int((now - visit.seated_at).total_seconds() / 60)

    # Mark table as dirty
    table_service = TableService(session)
    await table_service.clear_table(visit.table_id)

    await session.commit()
    await session.refresh(visit)

    return VisitRead.model_validate(visit)


@router.post("/visits/{visit_id}/transfer")
async def transfer_visit(
    visit_id: UUID,
    new_waiter_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> VisitRead:
    """
    Transfer a visit to another waiter.

    Records original waiter and transfer timestamp.
    """
    result = await session.execute(
        select(Visit).where(Visit.id == visit_id)
    )
    visit = result.scalar_one_or_none()

    if visit is None:
        raise HTTPException(status_code=404, detail="Visit not found")

    if visit.cleared_at:
        raise HTTPException(status_code=400, detail="Cannot transfer cleared visit")

    # Store original waiter if first transfer
    if visit.original_waiter_id is None:
        visit.original_waiter_id = visit.waiter_id

    visit.waiter_id = new_waiter_id
    visit.transferred_at = datetime.utcnow()

    await session.commit()
    await session.refresh(visit)

    return VisitRead.model_validate(visit)
