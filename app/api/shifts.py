"""
REST API endpoints for shift management.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.shift import Shift
from app.models.waiter import Waiter
from app.schemas.shift import ShiftCreate, ShiftRead, ShiftUpdate
from app.services.shift_service import ShiftService

router = APIRouter(prefix="/api/v1", tags=["shifts"])


@router.get("/restaurants/{restaurant_id}/shifts", response_model=List[ShiftRead])
async def list_shifts(
    restaurant_id: UUID,
    status: Optional[str] = Query(None, description="Filter by status (active, on_break, ended)"),
    waiter_id: Optional[UUID] = Query(None, description="Filter by waiter"),
    session: AsyncSession = Depends(get_session),
) -> List[ShiftRead]:
    """Get shifts for a restaurant."""
    query = select(Shift).where(Shift.restaurant_id == restaurant_id)

    if status:
        query = query.where(Shift.status == status)

    if waiter_id:
        query = query.where(Shift.waiter_id == waiter_id)

    query = query.order_by(Shift.clock_in.desc())

    result = await session.execute(query)
    shifts = result.scalars().all()

    return [ShiftRead.model_validate(s) for s in shifts]


@router.get("/restaurants/{restaurant_id}/shifts/active", response_model=List[ShiftRead])
async def list_active_shifts(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> List[ShiftRead]:
    """Get all currently active shifts."""
    result = await session.execute(
        select(Shift)
        .where(
            Shift.restaurant_id == restaurant_id,
            Shift.status.in_(["active", "on_break"]),
        )
        .order_by(Shift.clock_in)
    )
    shifts = result.scalars().all()

    return [ShiftRead.model_validate(s) for s in shifts]


@router.get("/shifts/{shift_id}", response_model=ShiftRead)
async def get_shift(
    shift_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ShiftRead:
    """Get a shift by ID."""
    result = await session.execute(
        select(Shift).where(Shift.id == shift_id)
    )
    shift = result.scalar_one_or_none()

    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")

    return ShiftRead.model_validate(shift)


@router.post("/shifts", response_model=ShiftRead)
async def clock_in(
    data: ShiftCreate,
    session: AsyncSession = Depends(get_session),
) -> ShiftRead:
    """
    Clock in a waiter (create a new shift).

    If waiter already has an active shift, returns error.
    """
    # Check waiter exists
    result = await session.execute(
        select(Waiter).where(Waiter.id == data.waiter_id)
    )
    waiter = result.scalar_one_or_none()
    if waiter is None:
        raise HTTPException(status_code=400, detail="Waiter not found")

    # Check no active shift exists
    result = await session.execute(
        select(Shift)
        .where(
            Shift.waiter_id == data.waiter_id,
            Shift.status.in_(["active", "on_break"]),
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Waiter already has active shift {existing.id}"
        )

    shift = Shift(
        restaurant_id=data.restaurant_id,
        waiter_id=data.waiter_id,
        section_id=data.section_id,
        clock_in=data.clock_in or datetime.utcnow(),
        status="active",
    )
    session.add(shift)
    await session.commit()
    await session.refresh(shift)

    return ShiftRead.model_validate(shift)


@router.patch("/shifts/{shift_id}", response_model=ShiftRead)
async def update_shift(
    shift_id: UUID,
    data: ShiftUpdate,
    session: AsyncSession = Depends(get_session),
) -> ShiftRead:
    """
    Update a shift (status change, clock out, etc).
    """
    result = await session.execute(
        select(Shift).where(Shift.id == shift_id)
    )
    shift = result.scalar_one_or_none()

    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")

    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)

    # If clocking out, set clock_out time if not provided
    if data.status == "ended" and shift.status != "ended":
        if "clock_out" not in update_data:
            update_data["clock_out"] = datetime.utcnow()

    for field, value in update_data.items():
        setattr(shift, field, value)

    await session.commit()
    await session.refresh(shift)

    return ShiftRead.model_validate(shift)


@router.post("/shifts/{shift_id}/break", response_model=ShiftRead)
async def take_break(
    shift_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ShiftRead:
    """Mark waiter as on break."""
    result = await session.execute(
        select(Shift).where(Shift.id == shift_id)
    )
    shift = result.scalar_one_or_none()

    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")

    if shift.status != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot take break - shift is {shift.status}"
        )

    shift.status = "on_break"
    await session.commit()
    await session.refresh(shift)

    return ShiftRead.model_validate(shift)


@router.post("/shifts/{shift_id}/resume", response_model=ShiftRead)
async def resume_shift(
    shift_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ShiftRead:
    """Resume shift from break."""
    result = await session.execute(
        select(Shift).where(Shift.id == shift_id)
    )
    shift = result.scalar_one_or_none()

    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")

    if shift.status != "on_break":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume - shift is {shift.status}"
        )

    shift.status = "active"
    await session.commit()
    await session.refresh(shift)

    return ShiftRead.model_validate(shift)


@router.post("/shifts/{shift_id}/end", response_model=ShiftRead)
async def clock_out(
    shift_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ShiftRead:
    """Clock out (end shift)."""
    result = await session.execute(
        select(Shift).where(Shift.id == shift_id)
    )
    shift = result.scalar_one_or_none()

    if shift is None:
        raise HTTPException(status_code=404, detail="Shift not found")

    if shift.status == "ended":
        raise HTTPException(status_code=400, detail="Shift already ended")

    shift.status = "ended"
    shift.clock_out = datetime.utcnow()
    await session.commit()
    await session.refresh(shift)

    return ShiftRead.model_validate(shift)
