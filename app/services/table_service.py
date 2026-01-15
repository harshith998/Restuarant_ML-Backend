"""Service for table operations."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.table import Table
from app.models.metrics import TableStateLog
from app.models.section import Section


class TableService:
    """Service for table state operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_available_tables(
        self,
        restaurant_id: UUID,
        min_capacity: int,
        preference: Optional[str] = None,
    ) -> Sequence[Table]:
        """
        Get tables that are available for seating.

        Filters:
        - state = 'clean'
        - capacity >= min_capacity
        - is_active = True

        Optionally filters by table_type preference.
        Returns tables sorted by capacity (smallest first).
        """
        stmt = (
            select(Table)
            .where(Table.restaurant_id == restaurant_id)
            .where(Table.state == "clean")
            .where(Table.capacity >= min_capacity)
            .where(Table.is_active == True)  # noqa: E712
            .order_by(Table.capacity)
        )

        if preference and preference != "none":
            stmt = stmt.where(Table.table_type == preference)

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_tables_in_sections(
        self,
        tables: Sequence[Table],
        section_ids: set[UUID],
    ) -> list[Table]:
        """Filter tables to only those in specified sections."""
        return [t for t in tables if t.section_id in section_ids]

    async def update_table_state(
        self,
        table_id: UUID,
        state: str,
        source: str,
        confidence: Optional[float] = None,
    ) -> Table:
        """
        Update table state and log the change.

        Creates TableStateLog entry for audit trail.
        """
        stmt = select(Table).where(Table.id == table_id)
        result = await self.session.execute(stmt)
        table = result.scalar_one_or_none()

        if table is None:
            raise ValueError(f"Table {table_id} not found")

        previous_state = table.state

        # Create log entry
        log = TableStateLog(
            table_id=table_id,
            previous_state=previous_state,
            new_state=state,
            confidence=confidence,
            source=source,
        )
        self.session.add(log)

        # Update table
        table.state = state
        table.state_confidence = confidence
        table.state_updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(table)

        return table

    async def get_floor_status(
        self,
        restaurant_id: UUID,
    ) -> list[dict]:
        """
        Get all tables with current state for floor view.

        Returns list of dicts with table info and section name.
        """
        stmt = (
            select(Table)
            .where(Table.restaurant_id == restaurant_id)
            .where(Table.is_active == True)  # noqa: E712
            .options(selectinload(Table.section))
            .order_by(Table.table_number)
        )

        result = await self.session.execute(stmt)
        tables = result.scalars().all()

        floor_data = []
        for table in tables:
            floor_data.append({
                "id": str(table.id),
                "table_number": table.table_number,
                "capacity": table.capacity,
                "table_type": table.table_type,
                "state": table.state,
                "state_confidence": float(table.state_confidence) if table.state_confidence else None,
                "state_updated_at": table.state_updated_at.isoformat() if table.state_updated_at else None,
                "current_visit_id": str(table.current_visit_id) if table.current_visit_id else None,
                "section_id": str(table.section_id) if table.section_id else None,
                "section_name": table.section.name if table.section else None,
            })

        return floor_data

    async def seat_table(
        self,
        table_id: UUID,
        visit_id: UUID,
    ) -> Table:
        """
        Mark table as occupied and link current visit.

        This is called after creating a Visit record.
        """
        stmt = select(Table).where(Table.id == table_id)
        result = await self.session.execute(stmt)
        table = result.scalar_one_or_none()

        if table is None:
            raise ValueError(f"Table {table_id} not found")

        previous_state = table.state

        # Log the state change
        log = TableStateLog(
            table_id=table_id,
            previous_state=previous_state,
            new_state="occupied",
            source="system",
        )
        self.session.add(log)

        # Update table
        table.state = "occupied"
        table.current_visit_id = visit_id
        table.state_updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(table)

        return table

    async def clear_table(
        self,
        table_id: UUID,
        source: str = "system",
    ) -> Table:
        """
        Mark table as dirty and clear current visit.

        Called when a visit ends (party leaves).
        """
        stmt = select(Table).where(Table.id == table_id)
        result = await self.session.execute(stmt)
        table = result.scalar_one_or_none()

        if table is None:
            raise ValueError(f"Table {table_id} not found")

        previous_state = table.state

        # Log the state change
        log = TableStateLog(
            table_id=table_id,
            previous_state=previous_state,
            new_state="dirty",
            source=source,
        )
        self.session.add(log)

        # Update table
        table.state = "dirty"
        table.current_visit_id = None
        table.state_updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(table)

        return table

    async def get_table_by_id(self, table_id: UUID) -> Optional[Table]:
        """Get a single table by ID."""
        stmt = select(Table).where(Table.id == table_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_sections_from_tables(self, tables: Sequence[Table]) -> set[UUID]:
        """Extract unique section IDs from a list of tables."""
        return {t.section_id for t in tables if t.section_id is not None}
