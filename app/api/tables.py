"""
REST API endpoints for table management.
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_session
from app.models.table import Table
from app.models.section import Section
from app.schemas.table import TableCreate, TableRead, TableUpdate, TableStateUpdate
from app.services.table_service import TableService
from app.services.table_state import update_table_state, get_table_state_history

router = APIRouter(prefix="/api/v1", tags=["tables"])


@router.get("/restaurants/{restaurant_id}/tables", response_model=List[TableRead])
async def list_tables(
    restaurant_id: UUID,
    state: Optional[str] = Query(None, description="Filter by state (clean, occupied, dirty)"),
    section_id: Optional[UUID] = Query(None, description="Filter by section"),
    include_inactive: bool = Query(False, description="Include inactive tables"),
    session: AsyncSession = Depends(get_session),
) -> List[TableRead]:
    """
    Get all tables for a restaurant.

    Optionally filter by state or section.
    """
    stmt = select(Table).where(Table.restaurant_id == restaurant_id)
    if state:
        stmt = stmt.where(Table.state == state)
    if section_id:
        stmt = stmt.where(Table.section_id == section_id)
    if not include_inactive:
        stmt = stmt.where(Table.is_active == True)  # noqa: E712
    stmt = stmt.order_by(Table.table_number)

    result = await session.execute(stmt)
    tables = result.scalars().all()

    return [TableRead.model_validate(t) for t in tables]


@router.get("/restaurants/{restaurant_id}/tables/section-view", response_model=List[dict])
async def get_section_view(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> List[dict]:
    """
    Get section view with all tables grouped by section.

    Includes section names and visit info for occupied tables.
    """
    service = TableService(session)
    return await service.get_floor_status(restaurant_id)


@router.get("/tables/{table_id}", response_model=TableRead)
async def get_table(
    table_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> TableRead:
    """Get a single table by ID."""
    service = TableService(session)
    table = await service.get_table_by_id(table_id)

    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")

    return TableRead.model_validate(table)


@router.post("/restaurants/{restaurant_id}/tables", response_model=TableRead)
async def create_table(
    restaurant_id: UUID,
    data: TableCreate,
    session: AsyncSession = Depends(get_session),
) -> TableRead:
    """Create a new table."""
    # Validate section exists if provided
    if data.section_id:
        result = await session.execute(
            select(Section).where(Section.id == data.section_id)
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Section not found")

    table = Table(
        restaurant_id=restaurant_id,
        section_id=data.section_id,
        table_number=data.table_number,
        capacity=data.capacity,
        table_type=data.table_type,
        location=data.location or "inside",
    )
    session.add(table)
    await session.commit()
    await session.refresh(table)

    return TableRead.model_validate(table)


@router.patch("/tables/{table_id}", response_model=TableRead)
async def update_table(
    table_id: UUID,
    data: TableUpdate,
    session: AsyncSession = Depends(get_session),
) -> TableRead:
    """Update table properties (not state - use PATCH /tables/{id}/state for that)."""
    result = await session.execute(select(Table).where(Table.id == table_id))
    table = result.scalar_one_or_none()

    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")

    # Update only provided fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(table, field, value)

    await session.commit()
    await session.refresh(table)

    return TableRead.model_validate(table)


@router.patch("/tables/{table_id}/state", response_model=TableRead)
async def update_state(
    table_id: UUID,
    data: TableStateUpdate,
    session: AsyncSession = Depends(get_session),
) -> TableRead:
    """
    Update table state (host override or ML update).

    This creates a TableStateLog entry for audit trail.
    """
    try:
        table = await update_table_state(
            session=session,
            table_id=table_id,
            new_state=data.state,
            confidence=data.confidence,
            source=data.source,
        )
        await session.commit()
        await session.refresh(table)
        return TableRead.model_validate(table)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/tables/{table_id}/history")
async def get_state_history(
    table_id: UUID,
    limit: int = Query(50, le=200, description="Max records to return"),
    session: AsyncSession = Depends(get_session),
) -> List[dict]:
    """
    Get state change history for a table.

    Useful for debugging ML accuracy and tracking manual overrides.
    """
    logs = await get_table_state_history(session, table_id, limit)

    return [
        {
            "id": str(log.id),
            "previous_state": log.previous_state,
            "new_state": log.new_state,
            "confidence": float(log.confidence) if log.confidence else None,
            "source": log.source,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@router.get("/restaurants/{restaurant_id}/tables/stats")
async def get_table_stats(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Get table statistics for a restaurant.

    Returns counts by state.
    """
    service = TableService(session)
    counts = await service.count_by_state(restaurant_id)

    total = sum(counts.values())

    return {
        "total": total,
        "by_state": counts,
        "available": counts.get("clean", 0),
        "occupied": counts.get("occupied", 0),
        "needs_cleaning": counts.get("dirty", 0),
    }
