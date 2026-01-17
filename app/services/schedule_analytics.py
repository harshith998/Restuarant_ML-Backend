"""Service for computing schedule performance analytics."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Schedule,
    ScheduleItem,
    StaffingRequirements,
    StaffPreference,
    Waiter,
)
from app.services.fairness_calculator import (
    FairnessCalculator,
    FairnessReport,
    StaffFairnessMetrics,
)
from app.services.scheduling_constraints import ShiftAssignment, StaffContext


# ============================================================================
# Dataclass Results
# ============================================================================


@dataclass
class DailyCoverage:
    """Coverage metrics for a single day."""

    date: date
    day_of_week: int
    slots_required: int
    slots_filled: int
    coverage_pct: float
    peak_hour: int = 0
    peak_coverage_pct: float = 0.0


@dataclass
class UnderstaffedSlot:
    """A time slot that didn't meet staffing requirements."""

    date: date
    day_of_week: int
    start_time: time
    end_time: time
    role: str
    required: int
    filled: int
    shortfall: int


@dataclass
class CoverageMetrics:
    """Coverage metrics for a schedule."""

    schedule_id: UUID
    week_start: date
    total_slots_required: int
    total_slots_filled: int
    coverage_pct: float
    daily_coverage: List[DailyCoverage] = field(default_factory=list)
    shift_coverage: Dict[str, float] = field(default_factory=dict)
    understaffed_slots: List[UnderstaffedSlot] = field(default_factory=list)


@dataclass
class StaffPreferenceMatch:
    """Preference match for a single staff member."""

    waiter_id: UUID
    waiter_name: str
    preference_score: float
    role_matched: bool
    shift_type_matched: bool
    section_matched: bool
    shifts_assigned: int


@dataclass
class PreferenceMatchMetrics:
    """Preference matching metrics for a schedule."""

    schedule_id: UUID
    avg_preference_score: float
    role_match_pct: float
    shift_type_match_pct: float
    section_match_pct: float
    by_staff: List[StaffPreferenceMatch] = field(default_factory=list)


@dataclass
class FairnessTrend:
    """Historical fairness metrics for a single week."""

    week_start: date
    gini_coefficient: float
    hours_std_dev: float
    prime_shift_gini: float
    is_balanced: bool
    staff_count: int


@dataclass
class FairnessHistory:
    """Historical fairness trends."""

    restaurant_id: UUID
    trends: List[FairnessTrend] = field(default_factory=list)
    avg_gini: float = 0.0
    trend_direction: str = "stable"  # improving, stable, declining
    weeks_analyzed: int = 0


# ============================================================================
# Service
# ============================================================================


class ScheduleAnalyticsService:
    """
    Service for computing schedule performance analytics.

    Provides metrics for:
    - Coverage (% slots filled, understaffing by day/shift)
    - Fairness (Gini coefficient trends, hours distribution)
    - Preference matching (avg scores, by staff breakdown)
    """

    # Shift type definitions (hour ranges)
    SHIFT_TYPES = {
        "morning": (6, 11),
        "afternoon": (11, 16),
        "evening": (16, 21),
        "closing": (21, 2),
    }

    DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    def __init__(self, session: AsyncSession):
        self.session = session
        self.fairness_calculator = FairnessCalculator()

    async def get_coverage_metrics(self, schedule_id: UUID) -> CoverageMetrics:
        """
        Calculate coverage metrics for a schedule.

        Compares schedule items against staffing requirements to determine:
        - Overall coverage percentage
        - Daily coverage breakdown
        - Understaffed slots (where requirements weren't met)
        """
        # Load schedule with items
        schedule = await self._load_schedule(schedule_id)
        if not schedule:
            return CoverageMetrics(
                schedule_id=schedule_id,
                week_start=date.today(),
                total_slots_required=0,
                total_slots_filled=0,
                coverage_pct=100.0,  # No requirements = 100%
            )

        # Load staffing requirements
        requirements = await self._load_staffing_requirements(schedule.restaurant_id)

        if not requirements:
            # No requirements defined = 100% coverage
            return CoverageMetrics(
                schedule_id=schedule_id,
                week_start=schedule.week_start_date,
                total_slots_required=0,
                total_slots_filled=len(schedule.items),
                coverage_pct=100.0,
            )

        # Calculate coverage
        daily_coverage = []
        understaffed_slots = []
        shift_coverage_counts: Dict[str, Tuple[int, int]] = {}  # {type: (filled, required)}
        total_required = 0
        total_filled = 0

        for day_offset in range(7):
            day_date = schedule.week_start_date + timedelta(days=day_offset)
            day_of_week = day_date.weekday()

            # Get requirements for this day
            day_requirements = [r for r in requirements if r.day_of_week == day_of_week]

            day_required = 0
            day_filled = 0

            for req in day_requirements:
                # Count items that match this requirement
                matching_items = [
                    item for item in schedule.items
                    if (
                        item.shift_date == day_date
                        and item.role == req.role
                        and self._times_overlap(
                            item.shift_start, item.shift_end,
                            req.start_time, req.end_time
                        )
                    )
                ]

                filled = len(matching_items)
                required = req.min_staff

                day_required += required
                day_filled += min(filled, required)

                # Track shift type coverage
                shift_type = self._get_shift_type(req.start_time)
                if shift_type not in shift_coverage_counts:
                    shift_coverage_counts[shift_type] = (0, 0)
                prev_filled, prev_required = shift_coverage_counts[shift_type]
                shift_coverage_counts[shift_type] = (
                    prev_filled + min(filled, required),
                    prev_required + required
                )

                # Track understaffed slots
                if filled < required:
                    understaffed_slots.append(UnderstaffedSlot(
                        date=day_date,
                        day_of_week=day_of_week,
                        start_time=req.start_time,
                        end_time=req.end_time,
                        role=req.role,
                        required=required,
                        filled=filled,
                        shortfall=required - filled,
                    ))

            total_required += day_required
            total_filled += day_filled

            daily_coverage.append(DailyCoverage(
                date=day_date,
                day_of_week=day_of_week,
                slots_required=day_required,
                slots_filled=day_filled,
                coverage_pct=round((day_filled / day_required * 100) if day_required > 0 else 100.0, 1),
            ))

        # Calculate shift type coverage percentages
        shift_coverage = {}
        for shift_type, (filled, required) in shift_coverage_counts.items():
            shift_coverage[shift_type] = round(
                (filled / required * 100) if required > 0 else 100.0, 1
            )

        return CoverageMetrics(
            schedule_id=schedule_id,
            week_start=schedule.week_start_date,
            total_slots_required=total_required,
            total_slots_filled=total_filled,
            coverage_pct=round((total_filled / total_required * 100) if total_required > 0 else 100.0, 1),
            daily_coverage=daily_coverage,
            shift_coverage=shift_coverage,
            understaffed_slots=understaffed_slots,
        )

    async def get_fairness_metrics(self, schedule_id: UUID) -> FairnessReport:
        """
        Calculate fairness metrics for a schedule.

        Leverages existing FairnessCalculator to compute:
        - Gini coefficient for hours distribution
        - Prime shift distribution
        - Per-staff fairness scores
        """
        # Load schedule with items and waiter info
        schedule = await self._load_schedule(schedule_id)
        if not schedule or not schedule.items:
            return FairnessReport(
                schedule_id=schedule_id,
                is_balanced=True,
            )

        # Build staff context from schedule items
        staff_map: Dict[UUID, StaffContext] = {}
        waiter_ids = {item.waiter_id for item in schedule.items}

        # Load waiters
        waiters = await self._load_waiters(list(waiter_ids))
        waiter_lookup = {w.id: w for w in waiters}

        # Load preferences
        preferences = await self._load_preferences(list(waiter_ids))
        pref_lookup = {p.waiter_id: p for p in preferences}

        for item in schedule.items:
            waiter = waiter_lookup.get(item.waiter_id)
            if not waiter:
                continue

            if item.waiter_id not in staff_map:
                pref = pref_lookup.get(item.waiter_id)
                staff_map[item.waiter_id] = StaffContext(
                    waiter_id=item.waiter_id,
                    name=waiter.name,
                    role=waiter.role or "server",
                    is_active=waiter.is_active,
                    max_hours_per_week=pref.max_hours_per_week if pref else None,
                    min_hours_per_week=pref.min_hours_per_week if pref else None,
                )

            # Add shift assignment
            staff_map[item.waiter_id].assigned_shifts.append(
                ShiftAssignment(
                    waiter_id=item.waiter_id,
                    shift_date=item.shift_date,
                    shift_start=item.shift_start,
                    shift_end=item.shift_end,
                    role=item.role,
                    section_id=item.section_id,
                )
            )

        # Calculate fairness
        staff_list = list(staff_map.values())
        report = self.fairness_calculator.calculate_schedule_fairness(staff_list)
        report.schedule_id = schedule_id
        report.week_start = schedule.week_start_date

        return report

    async def get_preference_match_metrics(self, schedule_id: UUID) -> PreferenceMatchMetrics:
        """
        Calculate how well the schedule matches staff preferences.

        Analyzes:
        - Role preference matching
        - Shift type preference matching
        - Section preference matching
        - Per-staff breakdown
        """
        schedule = await self._load_schedule(schedule_id)
        if not schedule or not schedule.items:
            return PreferenceMatchMetrics(
                schedule_id=schedule_id,
                avg_preference_score=100.0,  # No items = perfect match
                role_match_pct=100.0,
                shift_type_match_pct=100.0,
                section_match_pct=100.0,
            )

        waiter_ids = {item.waiter_id for item in schedule.items}

        # Load waiters and preferences
        waiters = await self._load_waiters(list(waiter_ids))
        waiter_lookup = {w.id: w for w in waiters}

        preferences = await self._load_preferences(list(waiter_ids))
        pref_lookup = {p.waiter_id: p for p in preferences}

        # Track matches per staff
        staff_matches: Dict[UUID, Dict] = {}
        total_role_matches = 0
        total_shift_type_matches = 0
        total_section_matches = 0
        total_items = 0

        for item in schedule.items:
            waiter = waiter_lookup.get(item.waiter_id)
            if not waiter:
                continue

            pref = pref_lookup.get(item.waiter_id)

            if item.waiter_id not in staff_matches:
                staff_matches[item.waiter_id] = {
                    "name": waiter.name,
                    "role_matches": 0,
                    "shift_type_matches": 0,
                    "section_matches": 0,
                    "total_shifts": 0,
                }

            staff_matches[item.waiter_id]["total_shifts"] += 1
            total_items += 1

            # Check role match
            role_matched = False
            if pref and pref.preferred_roles:
                if item.role in pref.preferred_roles:
                    role_matched = True
                    staff_matches[item.waiter_id]["role_matches"] += 1
                    total_role_matches += 1
            else:
                # No preference = match
                role_matched = True
                staff_matches[item.waiter_id]["role_matches"] += 1
                total_role_matches += 1

            # Check shift type match
            shift_type = self._get_shift_type(item.shift_start)
            shift_type_matched = False
            if pref and pref.preferred_shift_types:
                if shift_type in pref.preferred_shift_types:
                    shift_type_matched = True
                    staff_matches[item.waiter_id]["shift_type_matches"] += 1
                    total_shift_type_matches += 1
            else:
                shift_type_matched = True
                staff_matches[item.waiter_id]["shift_type_matches"] += 1
                total_shift_type_matches += 1

            # Check section match
            section_matched = False
            if pref and pref.preferred_sections and item.section_id:
                if str(item.section_id) in [str(s) for s in pref.preferred_sections]:
                    section_matched = True
                    staff_matches[item.waiter_id]["section_matches"] += 1
                    total_section_matches += 1
            else:
                section_matched = True
                staff_matches[item.waiter_id]["section_matches"] += 1
                total_section_matches += 1

        # Build per-staff breakdown
        by_staff = []
        for waiter_id, data in staff_matches.items():
            total = data["total_shifts"]
            if total == 0:
                continue

            score = (
                (data["role_matches"] / total * 33.33) +
                (data["shift_type_matches"] / total * 33.33) +
                (data["section_matches"] / total * 33.34)
            )

            by_staff.append(StaffPreferenceMatch(
                waiter_id=waiter_id,
                waiter_name=data["name"],
                preference_score=round(score, 1),
                role_matched=data["role_matches"] == total,
                shift_type_matched=data["shift_type_matches"] == total,
                section_matched=data["section_matches"] == total,
                shifts_assigned=total,
            ))

        # Calculate overall percentages
        role_match_pct = round((total_role_matches / total_items * 100) if total_items > 0 else 100.0, 1)
        shift_type_match_pct = round((total_shift_type_matches / total_items * 100) if total_items > 0 else 100.0, 1)
        section_match_pct = round((total_section_matches / total_items * 100) if total_items > 0 else 100.0, 1)

        avg_score = (role_match_pct + shift_type_match_pct + section_match_pct) / 3

        return PreferenceMatchMetrics(
            schedule_id=schedule_id,
            avg_preference_score=round(avg_score, 1),
            role_match_pct=role_match_pct,
            shift_type_match_pct=shift_type_match_pct,
            section_match_pct=section_match_pct,
            by_staff=by_staff,
        )

    async def get_fairness_history(
        self,
        restaurant_id: UUID,
        weeks: int = 12,
    ) -> FairnessHistory:
        """
        Get historical fairness trends for a restaurant.

        Analyzes published schedules over time to show:
        - Gini coefficient trend
        - Whether fairness is improving/declining
        """
        # Load published schedules
        stmt = (
            select(Schedule)
            .where(Schedule.restaurant_id == restaurant_id)
            .where(Schedule.status == "published")
            .order_by(Schedule.week_start_date.desc())
            .limit(weeks)
            .options(selectinload(Schedule.items))
        )
        result = await self.session.execute(stmt)
        schedules = result.scalars().all()

        if not schedules:
            return FairnessHistory(
                restaurant_id=restaurant_id,
                trend_direction="stable",
                weeks_analyzed=0,
            )

        trends = []
        gini_values = []

        for schedule in reversed(schedules):  # Oldest first
            # Calculate fairness for this schedule
            report = await self.get_fairness_metrics(schedule.id)

            trends.append(FairnessTrend(
                week_start=schedule.week_start_date,
                gini_coefficient=report.gini_coefficient,
                hours_std_dev=report.hours_std_dev,
                prime_shift_gini=report.prime_shift_gini,
                is_balanced=report.is_balanced,
                staff_count=len(report.staff_metrics),
            ))
            gini_values.append(report.gini_coefficient)

        # Calculate average and trend direction
        avg_gini = sum(gini_values) / len(gini_values) if gini_values else 0.0

        # Determine trend direction
        trend_direction = "stable"
        if len(gini_values) >= 3:
            first_half = gini_values[:len(gini_values)//2]
            second_half = gini_values[len(gini_values)//2:]

            first_avg = sum(first_half) / len(first_half)
            second_avg = sum(second_half) / len(second_half)

            diff = second_avg - first_avg
            if diff < -0.02:  # Lower Gini = improving
                trend_direction = "improving"
            elif diff > 0.02:  # Higher Gini = declining
                trend_direction = "declining"

        return FairnessHistory(
            restaurant_id=restaurant_id,
            trends=trends,
            avg_gini=round(avg_gini, 3),
            trend_direction=trend_direction,
            weeks_analyzed=len(trends),
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _load_schedule(self, schedule_id: UUID) -> Optional[Schedule]:
        """Load a schedule with its items."""
        stmt = (
            select(Schedule)
            .where(Schedule.id == schedule_id)
            .options(selectinload(Schedule.items))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_staffing_requirements(
        self,
        restaurant_id: UUID,
    ) -> List[StaffingRequirements]:
        """Load staffing requirements for a restaurant."""
        stmt = (
            select(StaffingRequirements)
            .where(StaffingRequirements.restaurant_id == restaurant_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _load_waiters(self, waiter_ids: List[UUID]) -> List[Waiter]:
        """Load waiters by IDs."""
        if not waiter_ids:
            return []
        stmt = select(Waiter).where(Waiter.id.in_(waiter_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _load_preferences(self, waiter_ids: List[UUID]) -> List[StaffPreference]:
        """Load staff preferences by waiter IDs."""
        if not waiter_ids:
            return []
        stmt = select(StaffPreference).where(StaffPreference.waiter_id.in_(waiter_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def _times_overlap(
        self,
        start1: time,
        end1: time,
        start2: time,
        end2: time,
    ) -> bool:
        """Check if two time ranges overlap."""
        def to_minutes(t: time) -> int:
            return t.hour * 60 + t.minute

        s1, e1 = to_minutes(start1), to_minutes(end1)
        s2, e2 = to_minutes(start2), to_minutes(end2)

        # Handle overnight shifts
        if e1 < s1:
            e1 += 24 * 60
        if e2 < s2:
            e2 += 24 * 60

        return not (e1 <= s2 or e2 <= s1)

    def _get_shift_type(self, start_time: time) -> str:
        """Determine shift type based on start time."""
        hour = start_time.hour

        if 6 <= hour < 11:
            return "morning"
        elif 11 <= hour < 16:
            return "afternoon"
        elif 16 <= hour < 21:
            return "evening"
        else:
            return "closing"

    @staticmethod
    def rate_gini(gini: float) -> str:
        """Convert Gini coefficient to human-readable rating."""
        if gini < 0.10:
            return "excellent"
        elif gini < 0.20:
            return "good"
        elif gini < 0.30:
            return "fair"
        else:
            return "poor"
