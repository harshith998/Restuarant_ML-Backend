"""Table state management service.

Handles updating table states from ML predictions and manual overrides.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.table import Table
from app.models.metrics import TableStateLog


async def update_table_state(
    session: AsyncSession,
    table_id: UUID,
    new_state: str,
    confidence: Optional[float] = None,
    source: str = "ml",
) -> Table:
    """
    Update a table's state and log the change.

    Args:
        session: Database session
        table_id: UUID of the table to update
        new_state: New state ("clean", "occupied", "dirty", "reserved", "unavailable")
        confidence: ML confidence score (0-1), optional
        source: Source of update ("ml", "host", "system")

    Returns:
        Updated Table object

    Raises:
        ValueError: If table not found
    """
    # Get the table
    result = await session.execute(select(Table).where(Table.id == table_id))
    table = result.scalar_one_or_none()

    if table is None:
        raise ValueError(f"Table with id {table_id} not found")

    # Get previous state for logging
    previous_state = table.state

    # Only update if state actually changed
    if previous_state != new_state:
        # Create state log entry
        state_log = TableStateLog(
            table_id=table_id,
            previous_state=previous_state,
            new_state=new_state,
            confidence=confidence,
            source=source,
        )
        session.add(state_log)

        # Update table
        table.state = new_state
        table.state_confidence = confidence
        table.state_updated_at = datetime.utcnow()

        await session.flush()

    return table


async def get_table_state_history(
    session: AsyncSession,
    table_id: UUID,
    limit: int = 50,
) -> list[TableStateLog]:
    """
    Get state change history for a table.

    Args:
        session: Database session
        table_id: UUID of the table
        limit: Max number of records to return

    Returns:
        List of TableStateLog entries, most recent first
    """
    result = await session.execute(
        select(TableStateLog)
        .where(TableStateLog.table_id == table_id)
        .order_by(TableStateLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
