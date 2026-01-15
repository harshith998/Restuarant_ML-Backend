"""
REST API endpoints for waitlist management.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.waitlist import WaitlistEntry
from app.schemas.waitlist import WaitlistCreate, WaitlistRead, WaitlistUpdate

router = APIRouter(prefix="/api/v1", tags=["waitlist"])


@router.get("/restaurants/{restaurant_id}/waitlist", response_model=List[WaitlistRead])
async def list_waitlist(
    restaurant_id: UUID,
    status: Optional[str] = Query("waiting", description="Filter by status"),
    session: AsyncSession = Depends(get_session),
) -> List[WaitlistRead]:
    """
    Get waitlist entries for a restaurant.

    Default shows only waiting parties (not yet seated).
    """
    query = select(WaitlistEntry).where(
        WaitlistEntry.restaurant_id == restaurant_id
    )

    if status:
        query = query.where(WaitlistEntry.status == status)

    query = query.order_by(WaitlistEntry.checked_in_at)

    result = await session.execute(query)
    entries = result.scalars().all()

    return [WaitlistRead.model_validate(e) for e in entries]


@router.get("/restaurants/{restaurant_id}/waitlist/queue")
async def get_queue(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Get waitlist queue with wait time estimates.
    """
    result = await session.execute(
        select(WaitlistEntry)
        .where(
            WaitlistEntry.restaurant_id == restaurant_id,
            WaitlistEntry.status == "waiting",
        )
        .order_by(WaitlistEntry.checked_in_at)
    )
    entries = result.scalars().all()

    now = datetime.utcnow()
    queue = []
    for i, entry in enumerate(entries):
        wait_so_far = int((now - entry.checked_in_at).total_seconds() / 60)
        queue.append({
            "position": i + 1,
            "id": str(entry.id),
            "party_name": entry.party_name,
            "party_size": entry.party_size,
            "table_preference": entry.table_preference,
            "location_preference": entry.location_preference,
            "checked_in_at": entry.checked_in_at.isoformat(),
            "wait_so_far_minutes": wait_so_far,
            "quoted_wait_minutes": entry.quoted_wait_minutes,
        })

    return {
        "total_waiting": len(queue),
        "queue": queue,
    }


@router.get("/waitlist/{entry_id}", response_model=WaitlistRead)
async def get_entry(
    entry_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> WaitlistRead:
    """Get a waitlist entry by ID."""
    result = await session.execute(
        select(WaitlistEntry).where(WaitlistEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()

    if entry is None:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")

    return WaitlistRead.model_validate(entry)


@router.post("/restaurants/{restaurant_id}/waitlist", response_model=WaitlistRead)
async def add_to_waitlist(
    restaurant_id: UUID,
    data: WaitlistCreate,
    session: AsyncSession = Depends(get_session),
) -> WaitlistRead:
    """
    Add a party to the waitlist.
    """
    entry = WaitlistEntry(
        restaurant_id=restaurant_id,
        party_name=data.party_name,
        party_size=data.party_size,
        table_preference=data.table_preference,
        location_preference=data.location_preference,
        notes=data.notes,
        quoted_wait_minutes=data.quoted_wait_minutes,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    return WaitlistRead.model_validate(entry)


@router.patch("/waitlist/{entry_id}", response_model=WaitlistRead)
async def update_entry(
    entry_id: UUID,
    data: WaitlistUpdate,
    session: AsyncSession = Depends(get_session),
) -> WaitlistRead:
    """Update a waitlist entry."""
    result = await session.execute(
        select(WaitlistEntry).where(WaitlistEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()

    if entry is None:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")

    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)

    # Handle status transitions
    if data.status == "walked_away" and entry.status == "waiting":
        update_data["walked_away_at"] = datetime.utcnow()

    for field, value in update_data.items():
        setattr(entry, field, value)

    await session.commit()
    await session.refresh(entry)

    return WaitlistRead.model_validate(entry)


@router.post("/waitlist/{entry_id}/walk-away", response_model=WaitlistRead)
async def mark_walked_away(
    entry_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> WaitlistRead:
    """Mark party as walked away (gave up waiting)."""
    result = await session.execute(
        select(WaitlistEntry).where(WaitlistEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()

    if entry is None:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")

    if entry.status != "waiting":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot mark as walked away - status is {entry.status}"
        )

    entry.status = "walked_away"
    entry.walked_away_at = datetime.utcnow()
    await session.commit()
    await session.refresh(entry)

    return WaitlistRead.model_validate(entry)


@router.delete("/waitlist/{entry_id}")
async def delete_entry(
    entry_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Delete a waitlist entry (only if still waiting)."""
    result = await session.execute(
        select(WaitlistEntry).where(WaitlistEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()

    if entry is None:
        raise HTTPException(status_code=404, detail="Waitlist entry not found")

    if entry.status != "waiting":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete - status is {entry.status}"
        )

    session.delete(entry)
    await session.commit()

    return {"status": "deleted", "id": str(entry_id)}
