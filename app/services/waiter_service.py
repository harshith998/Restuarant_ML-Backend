"""Service for waiter operations and scoring."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.waiter import Waiter
from app.models.shift import Shift
from app.models.visit import Visit
from app.schemas.waiter import WaiterWithShiftStats


@dataclass
class RoutingConfig:
    """Routing configuration from restaurant.config."""

    mode: str = "section"
    max_tables_per_waiter: int = 5
    efficiency_weight: float = 1.0
    workload_penalty: float = 3.0
    tip_penalty: float = 2.0
    recency_penalty_minutes: int = 5
    recency_penalty_weight: float = 1.5


class WaiterService:
    """Service for waiter operations and scoring."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active_waiters(
        self,
        restaurant_id: UUID,
    ) -> list[WaiterWithShiftStats]:
        """
        Get all waiters with active or on_break shifts.

        Returns WaiterWithShiftStats which includes current shift data.
        """
        stmt = (
            select(Waiter, Shift)
            .join(Shift, Waiter.id == Shift.waiter_id)
            .where(Shift.restaurant_id == restaurant_id)
            .where(Shift.status.in_(["active", "on_break"]))
            .where(Waiter.is_active == True)  # noqa: E712
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        waiters_with_stats = []
        for waiter, shift in rows:
            # Count active visits (tables currently being served)
            current_tables = await self._count_active_visits(shift.id)

            waiters_with_stats.append(
                WaiterWithShiftStats(
                    id=waiter.id,
                    restaurant_id=waiter.restaurant_id,
                    name=waiter.name,
                    email=waiter.email,
                    phone=waiter.phone,
                    tier=waiter.tier,
                    composite_score=float(waiter.composite_score),
                    tier_updated_at=waiter.tier_updated_at,
                    total_shifts=waiter.total_shifts,
                    total_covers=waiter.total_covers,
                    total_tips=float(waiter.total_tips),
                    is_active=waiter.is_active,
                    created_at=waiter.created_at,
                    updated_at=waiter.updated_at,
                    # Current shift stats
                    current_tables=current_tables,
                    current_tips=float(shift.total_tips),
                    current_covers=shift.total_covers,
                    section_id=shift.section_id,
                    status=shift.status,
                )
            )

        return waiters_with_stats

    async def get_available_waiters(
        self,
        restaurant_id: UUID,
        section_ids: Optional[set[UUID]] = None,
        max_tables: int = 5,
    ) -> list[WaiterWithShiftStats]:
        """
        Get waiters who can take more tables.

        Filters:
        - Has active shift (status = 'active', not 'on_break' or 'ended')
        - current_tables < max_tables
        - Optionally filter by section
        """
        all_active = await self.get_active_waiters(restaurant_id)

        available = []
        for waiter in all_active:
            # Must be active (not on break)
            if waiter.status != "active":
                continue

            # Must be under table limit
            if waiter.current_tables >= max_tables:
                continue

            # Filter by section if specified
            if section_ids and waiter.section_id not in section_ids:
                continue

            available.append(waiter)

        return available

    async def calculate_waiter_priority(
        self,
        waiter: WaiterWithShiftStats,
        total_tips_in_pool: float,
        config: RoutingConfig,
        last_seated_at: Optional[datetime] = None,
    ) -> float:
        """
        Calculate waiter priority score for routing.

        Formula from PRD:
        priority = (efficiency_score * EFFICIENCY_WEIGHT)
                 - (current_tables / max_tables * WORKLOAD_PENALTY)
                 - (tip_share * TIP_PENALTY)
                 - (recency_penalty)
        """
        # Efficiency component (higher is better)
        efficiency = waiter.composite_score * config.efficiency_weight

        # Workload penalty (more tables = lower priority)
        workload = (
            waiter.current_tables / config.max_tables_per_waiter
        ) * config.workload_penalty

        # Tip penalty (higher tip share = lower priority for fairness)
        if total_tips_in_pool > 0:
            tip_share = (waiter.current_tips / total_tips_in_pool) * config.tip_penalty
        else:
            tip_share = 0.0

        # Recency penalty (soft no-double-seat)
        recency = self._calculate_recency_penalty(last_seated_at, config)

        priority = efficiency - workload - tip_share - recency
        return priority

    def _calculate_recency_penalty(
        self,
        last_seated_at: Optional[datetime],
        config: RoutingConfig,
    ) -> float:
        """
        Calculate recency penalty for a waiter.

        Linear decay: full penalty at 0 minutes, zero at threshold.
        """
        if last_seated_at is None:
            return 0.0

        now = datetime.utcnow()
        minutes_since_seating = (now - last_seated_at).total_seconds() / 60

        if minutes_since_seating >= config.recency_penalty_minutes:
            # Outside penalty window
            return 0.0

        # Linear decay
        decay_factor = 1 - (minutes_since_seating / config.recency_penalty_minutes)
        penalty = decay_factor * config.recency_penalty_weight

        return penalty

    async def get_last_seating_time(
        self,
        waiter_id: UUID,
        shift_id: UUID,
    ) -> Optional[datetime]:
        """Get timestamp of waiter's most recent seating in current shift."""
        stmt = (
            select(Visit.seated_at)
            .where(Visit.waiter_id == waiter_id)
            .where(Visit.shift_id == shift_id)
            .order_by(Visit.seated_at.desc())
            .limit(1)
        )

        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()

        return row

    async def score_and_rank_waiters(
        self,
        waiters: list[WaiterWithShiftStats],
        config: RoutingConfig,
        shift_ids: Optional[dict[UUID, UUID]] = None,
    ) -> list[tuple[WaiterWithShiftStats, float]]:
        """
        Score all waiters and return sorted by priority (highest first).

        Args:
            waiters: List of waiters to score
            config: Routing configuration
            shift_ids: Optional mapping of waiter_id -> shift_id for recency lookup

        Returns:
            List of (waiter, priority_score) tuples sorted by priority descending
        """
        if not waiters:
            return []

        # Calculate total tips in pool for fairness calculation
        total_tips = sum(w.current_tips for w in waiters)

        scored = []
        for waiter in waiters:
            # Get last seating time if shift_ids provided
            last_seated_at = None
            if shift_ids and waiter.id in shift_ids:
                last_seated_at = await self.get_last_seating_time(
                    waiter.id, shift_ids[waiter.id]
                )

            priority = await self.calculate_waiter_priority(
                waiter=waiter,
                total_tips_in_pool=total_tips,
                config=config,
                last_seated_at=last_seated_at,
            )
            scored.append((waiter, priority))

        # Sort by priority descending (highest first)
        scored.sort(key=lambda x: x[1], reverse=True)

        return scored

    async def is_underserved(
        self,
        waiter: WaiterWithShiftStats,
        all_waiters: list[WaiterWithShiftStats],
        threshold_ratio: float = 0.5,
    ) -> bool:
        """
        Check if waiter is significantly underserved.

        Used to override recency penalty if waiter's covers/tips
        are significantly below average.
        """
        if len(all_waiters) <= 1:
            return False

        avg_covers = sum(w.current_covers for w in all_waiters) / len(all_waiters)
        avg_tips = sum(w.current_tips for w in all_waiters) / len(all_waiters)

        # Underserved if both covers AND tips are below threshold
        covers_ratio = waiter.current_covers / avg_covers if avg_covers > 0 else 1.0
        tips_ratio = waiter.current_tips / avg_tips if avg_tips > 0 else 1.0

        return covers_ratio < threshold_ratio and tips_ratio < threshold_ratio

    async def _count_active_visits(self, shift_id: UUID) -> int:
        """Count active (not cleared) visits for a shift."""
        stmt = (
            select(func.count(Visit.id))
            .where(Visit.shift_id == shift_id)
            .where(Visit.cleared_at.is_(None))
        )

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_waiter_by_id(self, waiter_id: UUID) -> Optional[Waiter]:
        """Get a single waiter by ID."""
        stmt = select(Waiter).where(Waiter.id == waiter_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_shift_for_waiter(self, waiter_id: UUID) -> Optional[Shift]:
        """Get waiter's current active shift."""
        stmt = (
            select(Shift)
            .where(Shift.waiter_id == waiter_id)
            .where(Shift.status.in_(["active", "on_break"]))
        )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
