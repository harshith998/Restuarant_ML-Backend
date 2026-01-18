"""Service for intelligent party routing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.restaurant import Restaurant
from app.models.table import Table
from app.models.visit import Visit
from app.models.waitlist import WaitlistEntry
from app.models.shift import Shift
from app.services.table_service import TableService
from app.services.waiter_service import WaiterService, RoutingConfig
from app.services.shift_service import ShiftService
from app.schemas.routing import RouteResponse, MatchDetails
from app.schemas.waiter import WaiterWithShiftStats


# Scoring weights for table selection
TYPE_MATCH_WEIGHT = 10.0
LOCATION_MATCH_WEIGHT = 10.0
CAPACITY_PENALTY_PER_SEAT = 2.0
BASE_TABLE_SCORE = 50.0


@dataclass
class ScoredTable:
    """A table with its routing score."""
    table: Table
    score: float
    type_matched: bool
    location_matched: bool


class RoutingService:
    """Service for intelligent party routing."""

    def __init__(
        self,
        session: AsyncSession,
        table_service: Optional[TableService] = None,
        waiter_service: Optional[WaiterService] = None,
        shift_service: Optional[ShiftService] = None,
    ):
        self.session = session
        self.table_service = table_service or TableService(session)
        self.waiter_service = waiter_service or WaiterService(session)
        self.shift_service = shift_service or ShiftService(session)

    async def route_party(
        self,
        restaurant_id: UUID,
        party_size: Optional[int] = None,
        table_preference: Optional[str] = None,
        location_preference: Optional[str] = None,
        waitlist_id: Optional[UUID] = None,
    ) -> RouteResponse:
        """
        Route a party to the optimal table and waiter.

        Args:
            restaurant_id: The restaurant ID
            party_size: Size of the party (required if no waitlist_id)
            table_preference: Preferred table type (booth/bar/table)
            location_preference: Preferred location (inside/outside/patio)
            waitlist_id: If provided, uses waitlist entry's preferences

        Returns:
            RouteResponse with table and waiter assignment
        """
        # Load restaurant config
        restaurant = await self._get_restaurant(restaurant_id)
        if restaurant is None:
            return RouteResponse(
                success=False,
                message=f"Restaurant {restaurant_id} not found"
            )

        config = self._get_routing_config(restaurant)

        # If from waitlist, load party info
        if waitlist_id:
            waitlist_entry = await self._get_waitlist_entry(waitlist_id)
            if waitlist_entry is None:
                return RouteResponse(
                    success=False,
                    message=f"Waitlist entry {waitlist_id} not found"
                )
            party_size = waitlist_entry.party_size
            table_preference = waitlist_entry.table_preference
            location_preference = waitlist_entry.location_preference

        if party_size is None:
            return RouteResponse(
                success=False,
                message="party_size is required"
            )

        # Get available tables
        available_tables = await self.table_service.get_available_tables(
            restaurant_id=restaurant_id,
            min_capacity=party_size,
        )

        if not available_tables:
            return RouteResponse(
                success=False,
                message="No available tables for this party size"
            )

        # Score all tables
        scored_tables = self._score_tables(
            tables=available_tables,
            party_size=party_size,
            table_preference=table_preference,
            location_preference=location_preference,
        )

        # Route based on mode
        if config.mode == "rotation":
            return await self._route_rotation_mode(
                restaurant_id=restaurant_id,
                scored_tables=scored_tables,
                party_size=party_size,
                config=config,
            )
        else:
            return await self._route_section_mode(
                restaurant_id=restaurant_id,
                scored_tables=scored_tables,
                party_size=party_size,
                config=config,
            )

    def _score_tables(
        self,
        tables: Sequence[Table],
        party_size: int,
        table_preference: Optional[str] = None,
        location_preference: Optional[str] = None,
    ) -> list[ScoredTable]:
        """
        Score tables based on fit and preference matching.

        Higher score = better match.
        """
        scored = []

        for table in tables:
            score = BASE_TABLE_SCORE

            # Type matching
            type_matched = False
            if table_preference and table_preference != "none":
                if table.table_type == table_preference:
                    score += TYPE_MATCH_WEIGHT
                    type_matched = True

            # Location matching
            location_matched = False
            if location_preference and location_preference != "none":
                if table.location == location_preference:
                    score += LOCATION_MATCH_WEIGHT
                    location_matched = True

            # Capacity penalty - prefer smallest table that fits
            excess_capacity = table.capacity - party_size
            score -= excess_capacity * CAPACITY_PENALTY_PER_SEAT

            scored.append(ScoredTable(
                table=table,
                score=score,
                type_matched=type_matched,
                location_matched=location_matched,
            ))

        # Sort by score descending
        scored.sort(key=lambda x: x.score, reverse=True)

        return scored

    async def _route_section_mode(
        self,
        restaurant_id: UUID,
        scored_tables: list[ScoredTable],
        party_size: int,
        config: RoutingConfig,
    ) -> RouteResponse:
        """
        Route in section mode - only assign to waiters in valid sections.
        """
        # Get sections that have available tables
        section_ids = {st.table.section_id for st in scored_tables if st.table.section_id}

        # Get available waiters in those sections
        available_waiters = await self.waiter_service.get_available_waiters(
            restaurant_id=restaurant_id,
            section_ids=section_ids,
            max_tables=config.max_tables_per_waiter,
        )

        if not available_waiters:
            return RouteResponse(
                success=False,
                message="No available waiters in sections with tables"
            )

        # Build shift_id mapping for recency lookup
        shift_ids = {}
        for waiter in available_waiters:
            shift = await self.waiter_service.get_active_shift_for_waiter(waiter.id)
            if shift:
                shift_ids[waiter.id] = shift.id

        # Score and rank waiters
        ranked_waiters = await self.waiter_service.score_and_rank_waiters(
            waiters=available_waiters,
            config=config,
            shift_ids=shift_ids,
        )

        # Find best combination: highest priority waiter + best table in their section
        for waiter, priority in ranked_waiters:
            waiter_section = waiter.section_id

            # Find best table in this waiter's section
            for scored_table in scored_tables:
                if scored_table.table.section_id == waiter_section:
                    return await self._build_response(
                        table=scored_table.table,
                        waiter=waiter,
                        scored_table=scored_table,
                    )

        return RouteResponse(
            success=False,
            message="Could not find valid table/waiter combination"
        )

    async def _route_rotation_mode(
        self,
        restaurant_id: UUID,
        scored_tables: list[ScoredTable],
        party_size: int,
        config: RoutingConfig,
    ) -> RouteResponse:
        """
        Route in rotation mode - round-robin across all waiters.
        """
        # Get ALL available waiters (ignore sections)
        available_waiters = await self.waiter_service.get_available_waiters(
            restaurant_id=restaurant_id,
            section_ids=None,  # No section filter
            max_tables=config.max_tables_per_waiter,
        )

        if not available_waiters:
            return RouteResponse(
                success=False,
                message="No available waiters"
            )

        # Build shift_id mapping for recency lookup
        shift_ids = {}
        for waiter in available_waiters:
            shift = await self.waiter_service.get_active_shift_for_waiter(waiter.id)
            if shift:
                shift_ids[waiter.id] = shift.id

        # Score waiters - in rotation mode, recency is heavily weighted
        ranked_waiters = await self.waiter_service.score_and_rank_waiters(
            waiters=available_waiters,
            config=config,
            shift_ids=shift_ids,
        )

        # Best waiter + best table (any section)
        best_waiter, _ = ranked_waiters[0]
        best_table = scored_tables[0]

        return await self._build_response(
            table=best_table.table,
            waiter=best_waiter,
            scored_table=best_table,
        )

    async def seat_party(
        self,
        restaurant_id: UUID,
        table_id: UUID,
        waiter_id: UUID,
        party_size: int,
        waitlist_id: Optional[UUID] = None,
    ) -> Visit:
        """
        Execute seating after route decision.

        Creates Visit, updates Table state, updates Shift stats.
        """
        table = await self.table_service.get_table_by_id(table_id)
        if table is None:
            raise ValueError(f"Table {table_id} not found")
        if table.capacity < party_size:
            raise ValueError(
                f"Party size {party_size} exceeds table capacity {table.capacity}"
            )

        # Get waiter's active shift
        shift = await self.waiter_service.get_active_shift_for_waiter(waiter_id)
        if shift is None:
            raise ValueError(f"Waiter {waiter_id} has no active shift")

        # Create visit
        visit = Visit(
            restaurant_id=restaurant_id,
            table_id=table_id,
            waiter_id=waiter_id,
            shift_id=shift.id,
            waitlist_id=waitlist_id,
            party_size=party_size,
            seated_at=datetime.utcnow(),
        )
        self.session.add(visit)
        await self.session.flush()

        # Update table state
        await self.table_service.seat_table(table_id, visit.id)

        # Update shift stats
        await self.shift_service.update_shift_stats(
            shift_id=shift.id,
            tables_served_delta=1,
            covers_delta=party_size,
        )

        # Update waitlist entry if from waitlist
        if waitlist_id:
            await self._update_waitlist_seated(waitlist_id, visit.id)

        await self.session.commit()
        await self.session.refresh(visit)

        return visit

    async def switch_mode(
        self,
        restaurant_id: UUID,
        mode: str,
    ) -> bool:
        """
        Switch routing mode in restaurant config.

        Args:
            restaurant_id: The restaurant ID
            mode: New mode ('section' or 'rotation')

        Returns:
            True if successful
        """
        from sqlalchemy.orm.attributes import flag_modified

        if mode not in ("section", "rotation"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'section' or 'rotation'")

        restaurant = await self._get_restaurant(restaurant_id)
        if restaurant is None:
            raise ValueError(f"Restaurant {restaurant_id} not found")

        # Update config - must create new dict for SQLAlchemy to detect change
        config = dict(restaurant.config or {})
        if "routing" not in config:
            config["routing"] = {}
        else:
            config["routing"] = dict(config["routing"])
        config["routing"]["mode"] = mode
        restaurant.config = config

        # Flag as modified for SQLAlchemy to detect JSON changes
        flag_modified(restaurant, "config")

        await self.session.commit()

        return True

    async def _build_response(
        self,
        table: Table,
        waiter: WaiterWithShiftStats,
        scored_table: ScoredTable,
    ) -> RouteResponse:
        """Build the route response with all details."""
        # Get section name
        section_name = None
        if table.section_id:
            await self.session.refresh(table, ["section"])
            if table.section:
                section_name = table.section.name

        return RouteResponse(
            success=True,
            table_id=table.id,
            table_number=table.table_number,
            table_type=table.table_type,
            table_location=table.location,
            table_capacity=table.capacity,
            waiter_id=waiter.id,
            waiter_name=waiter.name,
            section_id=table.section_id,
            section_name=section_name,
            match_details=MatchDetails(
                type_matched=scored_table.type_matched,
                location_matched=scored_table.location_matched,
                capacity_fit=table.capacity,
            ),
        )

    def _get_routing_config(self, restaurant: Restaurant) -> RoutingConfig:
        """Extract routing config from restaurant with defaults."""
        config = (restaurant.config or {}).get("routing", {})
        return RoutingConfig(
            mode=config.get("mode", "section"),
            max_tables_per_waiter=config.get("max_tables_per_waiter", 5),
            efficiency_weight=config.get("efficiency_weight", 1.0),
            workload_penalty=config.get("workload_penalty", 3.0),
            tip_penalty=config.get("tip_penalty", 2.0),
            recency_penalty_minutes=config.get("recency_penalty_minutes", 5),
            recency_penalty_weight=config.get("recency_penalty_weight", 1.5),
        )

    async def _get_restaurant(self, restaurant_id: UUID) -> Optional[Restaurant]:
        """Get restaurant by ID."""
        stmt = select(Restaurant).where(Restaurant.id == restaurant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_waitlist_entry(self, waitlist_id: UUID) -> Optional[WaitlistEntry]:
        """Get waitlist entry by ID."""
        stmt = select(WaitlistEntry).where(WaitlistEntry.id == waitlist_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _update_waitlist_seated(self, waitlist_id: UUID, visit_id: UUID) -> None:
        """Update waitlist entry as seated."""
        stmt = select(WaitlistEntry).where(WaitlistEntry.id == waitlist_id)
        result = await self.session.execute(stmt)
        entry = result.scalar_one_or_none()

        if entry:
            entry.status = "seated"
            entry.seated_at = datetime.utcnow()
            entry.visit_id = visit_id
