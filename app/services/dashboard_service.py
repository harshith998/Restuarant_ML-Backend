"""Service for aggregating waiter dashboard data."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.waiter import Waiter
from app.models.shift import Shift
from app.models.visit import Visit
from app.models.insights import WaiterInsights
from app.schemas.insights import (
    WaiterStatsResponse,
    TrendDataPoint,
    WaiterInsightsResponse,
    RecentShiftResponse,
    WaiterDashboardResponse,
    WaiterProfileForDashboard,
)


class DashboardService:
    """
    Service for aggregating waiter dashboard data.

    Provides data for the waiter profile dashboard UI.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_waiter_stats(
        self,
        waiter_id: UUID,
        period: str = "month",
    ) -> WaiterStatsResponse:
        """
        Get stats for a waiter for a given period.

        Args:
            waiter_id: The waiter ID
            period: "month", "week", or "day"

        Returns:
            WaiterStatsResponse with covers, tips, etc.
        """
        # Determine date range
        today = date.today()
        if period == "month":
            start_date = today.replace(day=1)
        elif period == "week":
            start_date = today - timedelta(days=today.weekday())
        else:  # day
            start_date = today

        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(today, datetime.max.time())

        # Query visits in period
        stmt = (
            select(
                func.count(Visit.id).label("visits"),
                func.coalesce(func.sum(Visit.party_size), 0).label("covers"),
                func.coalesce(func.sum(Visit.tip), 0).label("tips"),
                func.coalesce(func.sum(Visit.total), 0).label("sales"),
            )
            .where(Visit.waiter_id == waiter_id)
            .where(Visit.seated_at >= start_dt)
            .where(Visit.seated_at <= end_dt)
        )

        result = await self.session.execute(stmt)
        row = result.one()

        visits = row.visits or 0
        covers = int(row.covers or 0)
        tips = float(row.tips or 0)
        sales = float(row.sales or 0)

        # Calculate averages
        avg_per_cover = sales / covers if covers > 0 else 0
        efficiency_pct = min(100, (covers / max(visits, 1)) * 10) if visits > 0 else 0

        return WaiterStatsResponse(
            covers=covers,
            tips=tips,
            avg_per_cover=round(avg_per_cover, 2),
            efficiency_pct=round(efficiency_pct, 1),
            tables_served=visits,
            total_sales=sales,
        )

    async def get_waiter_trends(
        self,
        waiter_id: UUID,
        months: int = 6,
    ) -> List[TrendDataPoint]:
        """
        Get monthly trend data for a waiter.

        Args:
            waiter_id: The waiter ID
            months: Number of months to look back

        Returns:
            List of TrendDataPoint for chart rendering
        """
        trends = []
        today = date.today()

        for i in range(months - 1, -1, -1):
            # Calculate month boundaries
            if i == 0:
                month_end = today
            else:
                # Go back i months
                month_end = today.replace(day=1) - timedelta(days=1)
                for _ in range(i - 1):
                    month_end = (month_end.replace(day=1) - timedelta(days=1))

            month_start = month_end.replace(day=1)
            month_key = month_start.strftime("%Y-%m")

            start_dt = datetime.combine(month_start, datetime.min.time())
            end_dt = datetime.combine(month_end, datetime.max.time())

            # Query visits for this month
            stmt = (
                select(
                    func.coalesce(func.sum(Visit.party_size), 0).label("covers"),
                    func.coalesce(func.sum(Visit.tip), 0).label("tips"),
                    func.coalesce(func.sum(Visit.total), 0).label("sales"),
                )
                .where(Visit.waiter_id == waiter_id)
                .where(Visit.seated_at >= start_dt)
                .where(Visit.seated_at <= end_dt)
            )

            result = await self.session.execute(stmt)
            row = result.one()

            covers = int(row.covers or 0)
            tips = float(row.tips or 0)
            sales = float(row.sales or 0)

            avg_tip_pct = (tips / sales * 100) if sales > 0 else None

            trends.append(TrendDataPoint(
                month=month_key,
                tips=tips,
                covers=covers,
                avg_tip_pct=round(avg_tip_pct, 1) if avg_tip_pct else None,
            ))

        return trends

    async def get_waiter_insights(
        self,
        waiter_id: UUID,
    ) -> Optional[WaiterInsightsResponse]:
        """
        Get the most recent LLM-generated insights for a waiter.

        Args:
            waiter_id: The waiter ID

        Returns:
            WaiterInsightsResponse or None if no insights exist
        """
        stmt = (
            select(WaiterInsights)
            .where(WaiterInsights.waiter_id == waiter_id)
            .order_by(WaiterInsights.computed_at.desc())
            .limit(1)
        )

        result = await self.session.execute(stmt)
        insights = result.scalar_one_or_none()

        if insights is None:
            # Return default insights based on waiter data
            waiter = await self._get_waiter(waiter_id)
            if waiter:
                tier = waiter.tier or "standard"
                score = float(waiter.composite_score or 50)

                # Generate tier-appropriate default insights
                if tier == "strong":
                    strengths = [
                        "Fast table turns (avg under 50min)",
                        "High tip percentage (20%+)",
                        "Excellent customer satisfaction",
                        "Great with large parties"
                    ]
                    areas_to_watch = [
                        "Could mentor newer staff"
                    ]
                    suggestions = [
                        "Consider wine pairing certification",
                        "Lead team training sessions"
                    ]
                    summary = f"{waiter.name} consistently delivers excellent service with fast table turns and high customer satisfaction. A top performer who sets the standard for the team."
                elif tier == "developing":
                    strengths = [
                        "Improving steadily each month",
                        "Good attitude and team player"
                    ]
                    areas_to_watch = [
                        "Table turn times above average",
                        "Upselling opportunities missed",
                        "Could improve menu knowledge"
                    ]
                    suggestions = [
                        "Shadow top performers during peak hours",
                        "Practice menu descriptions daily",
                        "Focus on drink upsells at greeting"
                    ]
                    summary = f"{waiter.name} is making steady progress and shows potential. Focused coaching on table management and upselling will accelerate improvement."
                else:  # standard
                    strengths = [
                        "Consistent performance",
                        "Reliable during busy periods",
                        "Good customer rapport"
                    ]
                    areas_to_watch = [
                        "Room for improvement on upsells",
                        "Could reduce table turn times"
                    ]
                    suggestions = [
                        "Try suggestive selling techniques",
                        "Work on multi-table management"
                    ]
                    summary = f"{waiter.name} delivers solid, consistent service. With focused effort on upselling and table management, could advance to top performer status."

                return WaiterInsightsResponse(
                    tier=tier,
                    composite_score=score,
                    math_score=score,
                    llm_score=score,
                    strengths=strengths,
                    areas_to_watch=areas_to_watch,
                    suggestions=suggestions,
                    llm_summary=summary,
                    computed_at=datetime.utcnow(),
                    llm_model="default-v1",
                )
            return None

        return WaiterInsightsResponse(
            tier=insights.tier or "standard",
            composite_score=float(insights.composite_score or 50),
            math_score=float(insights.math_score) if insights.math_score else None,
            llm_score=float(insights.llm_score) if insights.llm_score else None,
            strengths=insights.strengths or [],
            areas_to_watch=insights.areas_to_watch or [],
            suggestions=insights.suggestions or [],
            llm_summary=insights.llm_summary,
            computed_at=insights.computed_at,
            llm_model=insights.llm_model,
        )

    async def get_recent_shifts(
        self,
        waiter_id: UUID,
        limit: int = 10,
    ) -> List[RecentShiftResponse]:
        """
        Get recent shifts for a waiter.

        Args:
            waiter_id: The waiter ID
            limit: Maximum number of shifts to return

        Returns:
            List of RecentShiftResponse
        """
        stmt = (
            select(Shift)
            .where(Shift.waiter_id == waiter_id)
            .where(Shift.status == "ended")
            .order_by(Shift.clock_in.desc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        shifts = result.scalars().all()

        responses = []
        for shift in shifts:
            # Format hours
            hours = self._format_shift_hours(shift.clock_in, shift.clock_out)

            # Calculate efficiency (covers / hours worked)
            efficiency_pct = 0.0
            if shift.clock_out and shift.clock_in:
                hours_worked = (shift.clock_out - shift.clock_in).total_seconds() / 3600
                if hours_worked > 0:
                    efficiency_pct = min(100, (shift.total_covers / hours_worked) * 10)

            # Get section name if available
            section_name = None
            if shift.section_id:
                await self.session.refresh(shift, ["section"])
                if shift.section:
                    section_name = shift.section.name

            responses.append(RecentShiftResponse(
                id=shift.id,
                date=shift.clock_in.date(),
                clock_in=shift.clock_in,
                clock_out=shift.clock_out,
                hours=hours,
                covers=shift.total_covers,
                tips=float(shift.total_tips),
                sales=float(shift.total_sales),
                efficiency_pct=round(efficiency_pct, 1),
                section_name=section_name,
            ))

        return responses

    async def get_waiter_dashboard(
        self,
        waiter_id: UUID,
    ) -> Optional[WaiterDashboardResponse]:
        """
        Get complete dashboard data for a waiter.

        Combines all dashboard components into one response.

        Args:
            waiter_id: The waiter ID

        Returns:
            WaiterDashboardResponse or None if waiter not found
        """
        waiter = await self._get_waiter(waiter_id)
        if waiter is None:
            return None

        # Calculate tenure
        tenure_years = 0.0
        if waiter.created_at:
            tenure_days = (datetime.utcnow() - waiter.created_at).days
            tenure_years = round(tenure_days / 365.25, 2)

        # Build profile object
        profile = WaiterProfileForDashboard(
            id=waiter.id,
            name=waiter.name,
            tier=waiter.tier or "standard",
            tenure_years=tenure_years,
            email=waiter.email,
            phone=waiter.phone,
            total_shifts=waiter.total_shifts or 0,
            total_covers=waiter.total_covers or 0,
            total_tips=float(waiter.total_tips or 0),
            is_active=waiter.is_active,
            created_at=waiter.created_at,
        )

        # Use lifetime stats from waiter model (not period-based)
        covers = waiter.total_covers or 0
        tips = float(waiter.total_tips or 0)
        tables_served = waiter.total_tables_served or 0
        total_sales = float(waiter.total_sales or 0)

        stats = WaiterStatsResponse(
            covers=covers,
            tips=tips,
            avg_per_cover=round(total_sales / covers, 2) if covers > 0 else 0.0,
            efficiency_pct=round(min(100.0, (covers / tables_served) * 10), 1) if tables_served > 0 else 0.0,
            tables_served=tables_served,
            total_sales=total_sales,
        )

        # Get other dashboard components
        trends = await self.get_waiter_trends(waiter_id, months=6)
        insights = await self.get_waiter_insights(waiter_id)
        recent_shifts = await self.get_recent_shifts(waiter_id, limit=10)

        return WaiterDashboardResponse(
            profile=profile,
            stats=stats,
            trends=trends,
            insights=insights,
            recent_shifts=recent_shifts,
        )

    def _format_shift_hours(
        self,
        clock_in: datetime,
        clock_out: Optional[datetime],
    ) -> str:
        """Format shift hours like '4-11pm'."""
        def format_time(dt: datetime) -> str:
            hour = dt.hour
            if hour == 0:
                return "12am"
            elif hour < 12:
                return f"{hour}am"
            elif hour == 12:
                return "12pm"
            else:
                return f"{hour - 12}pm"

        start = format_time(clock_in)
        if clock_out:
            end = format_time(clock_out)
            return f"{start}-{end}"
        return f"{start}-?"

    async def _get_waiter(self, waiter_id: UUID) -> Optional[Waiter]:
        """Get waiter by ID."""
        stmt = select(Waiter).where(Waiter.id == waiter_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
