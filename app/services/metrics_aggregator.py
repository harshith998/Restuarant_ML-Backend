"""Service for aggregating waiter metrics from visits and shifts."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit import Visit
from app.models.shift import Shift
from app.models.waiter import Waiter


@dataclass
class WaiterMetricsSnapshot:
    """Aggregated metrics for a waiter over a time period."""

    waiter_id: UUID
    restaurant_id: UUID
    period_start: date
    period_end: date

    # Core metrics
    total_visits: int = 0
    total_covers: int = 0
    total_tips: float = 0.0
    total_sales: float = 0.0
    tables_served: int = 0
    shifts_worked: int = 0

    # Averages
    avg_turn_time_minutes: float = 0.0
    avg_tip_percentage: float = 0.0
    avg_check_size: float = 0.0
    avg_covers_per_shift: float = 0.0
    avg_tips_per_shift: float = 0.0

    # Efficiency
    efficiency_score: float = 0.0

    # Raw data for Z-score calculation
    turn_times: List[float] = field(default_factory=list)
    tip_percentages: List[float] = field(default_factory=list)


class MetricsAggregator:
    """
    Service for computing waiter metrics from raw visit and shift data.

    Used by the tier calculation job to gather 30-day rolling metrics.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def compute_waiter_metrics(
        self,
        waiter_id: UUID,
        days: int = 30,
        end_date: Optional[date] = None,
    ) -> WaiterMetricsSnapshot:
        """
        Compute aggregated metrics for a single waiter.

        Args:
            waiter_id: The waiter to compute metrics for
            days: Number of days to look back (default 30)
            end_date: End of the period (default today)

        Returns:
            WaiterMetricsSnapshot with all computed metrics
        """
        if end_date is None:
            end_date = date.today()

        period_start = end_date - timedelta(days=days)

        # Get waiter's restaurant
        waiter = await self._get_waiter(waiter_id)
        if waiter is None:
            raise ValueError(f"Waiter {waiter_id} not found")

        snapshot = WaiterMetricsSnapshot(
            waiter_id=waiter_id,
            restaurant_id=waiter.restaurant_id,
            period_start=period_start,
            period_end=end_date,
        )

        # Get visits in the period
        visits = await self._get_visits_in_period(waiter_id, period_start, end_date)

        if not visits:
            return snapshot

        # Aggregate visit data
        turn_times = []
        tip_percentages = []

        for visit in visits:
            snapshot.total_visits += 1
            snapshot.total_covers += visit.party_size or 0

            if visit.tip is not None:
                snapshot.total_tips += float(visit.tip)

            if visit.total is not None:
                snapshot.total_sales += float(visit.total)

                # Calculate tip percentage if we have both
                if visit.tip is not None and visit.total > 0:
                    tip_pct = (float(visit.tip) / float(visit.total)) * 100
                    tip_percentages.append(tip_pct)

            # Calculate turn time (seated to cleared)
            if visit.seated_at and visit.cleared_at:
                duration = (visit.cleared_at - visit.seated_at).total_seconds() / 60
                if duration > 0:
                    turn_times.append(duration)

        snapshot.tables_served = snapshot.total_visits
        snapshot.turn_times = turn_times
        snapshot.tip_percentages = tip_percentages

        # Calculate averages
        if turn_times:
            snapshot.avg_turn_time_minutes = sum(turn_times) / len(turn_times)

        if tip_percentages:
            snapshot.avg_tip_percentage = sum(tip_percentages) / len(tip_percentages)

        if snapshot.total_visits > 0:
            snapshot.avg_check_size = snapshot.total_sales / snapshot.total_visits

        # Get shifts in period
        shifts = await self._get_shifts_in_period(waiter_id, period_start, end_date)
        snapshot.shifts_worked = len(shifts)

        if snapshot.shifts_worked > 0:
            snapshot.avg_covers_per_shift = snapshot.total_covers / snapshot.shifts_worked
            snapshot.avg_tips_per_shift = snapshot.total_tips / snapshot.shifts_worked

        # Calculate efficiency score (simple heuristic)
        # Higher covers and lower turn time = more efficient
        if snapshot.avg_turn_time_minutes > 0:
            snapshot.efficiency_score = min(
                100,
                (snapshot.avg_covers_per_shift * 10) / (snapshot.avg_turn_time_minutes / 60)
            )

        return snapshot

    async def compute_all_waiter_metrics(
        self,
        restaurant_id: UUID,
        days: int = 30,
        end_date: Optional[date] = None,
    ) -> List[WaiterMetricsSnapshot]:
        """
        Compute metrics for all active waiters in a restaurant.

        Args:
            restaurant_id: The restaurant
            days: Number of days to look back
            end_date: End of the period

        Returns:
            List of WaiterMetricsSnapshot for each waiter
        """
        # Get all active waiters
        stmt = (
            select(Waiter)
            .where(Waiter.restaurant_id == restaurant_id)
            .where(Waiter.is_active == True)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        waiters = result.scalars().all()

        snapshots = []
        for waiter in waiters:
            try:
                snapshot = await self.compute_waiter_metrics(
                    waiter_id=waiter.id,
                    days=days,
                    end_date=end_date,
                )
                snapshots.append(snapshot)
            except Exception:
                # Skip waiters with errors, log in production
                continue

        return snapshots

    async def get_monthly_trends(
        self,
        waiter_id: UUID,
        months: int = 6,
    ) -> Dict[str, Dict]:
        """
        Get monthly aggregated data for trend chart.

        Returns dict like:
        {
            "2024-09": {"tips": 3800, "covers": 120, "avg_tip_pct": 18.5},
            "2024-10": {"tips": 4200, "covers": 135, "avg_tip_pct": 19.2},
            ...
        }
        """
        today = date.today()
        trends = {}

        for i in range(months):
            # Calculate month boundaries
            month_end = today.replace(day=1) - timedelta(days=1)
            if i > 0:
                for _ in range(i):
                    month_end = (month_end.replace(day=1) - timedelta(days=1))

            month_start = month_end.replace(day=1)
            month_key = month_start.strftime("%Y-%m")

            # Get visits for this month
            visits = await self._get_visits_in_period(
                waiter_id,
                month_start,
                month_end,
            )

            month_tips = sum(float(v.tip or 0) for v in visits)
            month_covers = sum(v.party_size or 0 for v in visits)
            month_sales = sum(float(v.total or 0) for v in visits)

            avg_tip_pct = 0.0
            if month_sales > 0:
                avg_tip_pct = (month_tips / month_sales) * 100

            trends[month_key] = {
                "tips": month_tips,
                "covers": month_covers,
                "avg_tip_pct": round(avg_tip_pct, 1),
            }

        return trends

    async def compute_peer_stats(
        self,
        restaurant_id: UUID,
        days: int = 30,
    ) -> Dict[str, float]:
        """
        Compute peer averages for a restaurant.

        Used for Z-score normalization context.

        Returns:
            {
                "avg_turn_time": float,
                "std_turn_time": float,
                "avg_tip_pct": float,
                "std_tip_pct": float,
                "avg_covers_per_shift": float,
                "std_covers_per_shift": float,
            }
        """
        all_metrics = await self.compute_all_waiter_metrics(restaurant_id, days)

        if not all_metrics:
            return {
                "avg_turn_time": 45.0,
                "std_turn_time": 10.0,
                "avg_tip_pct": 18.0,
                "std_tip_pct": 3.0,
                "avg_covers_per_shift": 20.0,
                "std_covers_per_shift": 5.0,
            }

        turn_times = [m.avg_turn_time_minutes for m in all_metrics if m.avg_turn_time_minutes > 0]
        tip_pcts = [m.avg_tip_percentage for m in all_metrics if m.avg_tip_percentage > 0]
        covers = [m.avg_covers_per_shift for m in all_metrics if m.avg_covers_per_shift > 0]

        def _mean(values: List[float]) -> float:
            return sum(values) / len(values) if values else 0.0

        def _std(values: List[float]) -> float:
            if len(values) < 2:
                return 1.0
            mean = _mean(values)
            variance = sum((x - mean) ** 2 for x in values) / len(values)
            return variance ** 0.5 or 1.0

        return {
            "avg_turn_time": _mean(turn_times) or 45.0,
            "std_turn_time": _std(turn_times) or 10.0,
            "avg_tip_pct": _mean(tip_pcts) or 18.0,
            "std_tip_pct": _std(tip_pcts) or 3.0,
            "avg_covers_per_shift": _mean(covers) or 20.0,
            "std_covers_per_shift": _std(covers) or 5.0,
        }

    async def _get_waiter(self, waiter_id: UUID) -> Optional[Waiter]:
        """Get waiter by ID."""
        stmt = select(Waiter).where(Waiter.id == waiter_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_visits_in_period(
        self,
        waiter_id: UUID,
        start_date: date,
        end_date: date,
    ) -> List[Visit]:
        """Get all visits for a waiter in a date range."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        stmt = (
            select(Visit)
            .where(Visit.waiter_id == waiter_id)
            .where(Visit.seated_at >= start_dt)
            .where(Visit.seated_at <= end_dt)
            .order_by(Visit.seated_at)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_shifts_in_period(
        self,
        waiter_id: UUID,
        start_date: date,
        end_date: date,
    ) -> List[Shift]:
        """Get all shifts for a waiter in a date range."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        stmt = (
            select(Shift)
            .where(Shift.waiter_id == waiter_id)
            .where(Shift.clock_in >= start_dt)
            .where(Shift.clock_in <= end_dt)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
