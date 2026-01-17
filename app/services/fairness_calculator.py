"""Service for calculating fairness metrics across staff schedules."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from app.services.scheduling_constraints import ShiftAssignment, StaffContext


@dataclass
class StaffFairnessMetrics:
    """Fairness metrics for a single staff member."""

    waiter_id: UUID
    name: str

    # Hours distribution
    weekly_hours: float
    hours_vs_target: float  # +/- from preferred hours

    # Prime shift access
    prime_shifts_count: int
    prime_shifts_hours: float

    # Historical context (if available)
    recent_prime_shift_ratio: float  # Last 4 weeks

    # Composite score (0-100, higher = more advantaged)
    fairness_score: float


@dataclass
class FairnessReport:
    """Fairness report for a complete schedule."""

    schedule_id: Optional[UUID] = None
    week_start: Optional[date] = None

    # Overall metrics
    gini_coefficient: float = 0.0  # 0=equal, 1=unequal
    hours_std_dev: float = 0.0
    prime_shift_gini: float = 0.0

    # Per-staff breakdown
    staff_metrics: List[StaffFairnessMetrics] = field(default_factory=list)

    # Flags
    fairness_issues: List[str] = field(default_factory=list)
    is_balanced: bool = True


class FairnessCalculator:
    """
    Calculates fairness metrics across staff.

    Fairness dimensions:
    1. Hours balance: Are hours distributed fairly?
    2. Prime shift balance: Are desirable shifts shared?
    3. Historical equity: Has this person been under/over-scheduled recently?

    Uses Gini coefficient to measure inequality (0 = perfect equality, 1 = maximum inequality).
    """

    # Thresholds
    GINI_THRESHOLD = 0.25  # Above this is considered unfair
    HOURS_IMBALANCE_THRESHOLD = 5.0  # Hours difference to flag

    def __init__(self):
        pass

    def calculate_schedule_fairness(
        self,
        staff_list: List[StaffContext],
        prime_shift_slots: Optional[List[Tuple[int, time, time]]] = None,
    ) -> FairnessReport:
        """
        Calculate fairness metrics for a complete schedule.

        Args:
            staff_list: List of staff with their assigned shifts
            prime_shift_slots: Optional list of (day_of_week, start, end) for prime shifts

        Returns:
            FairnessReport with overall and per-staff metrics
        """
        if not staff_list:
            return FairnessReport(is_balanced=True)

        # Calculate hours for each staff member
        hours_list = []
        prime_hours_list = []
        staff_metrics = []

        for staff in staff_list:
            weekly_hours = self._calculate_total_hours(staff.assigned_shifts)
            hours_list.append(weekly_hours)

            prime_shifts, prime_hours = self._count_prime_shifts(
                staff.assigned_shifts,
                prime_shift_slots or [],
            )
            prime_hours_list.append(prime_hours)

            # Calculate hours vs target
            target_hours = staff.max_hours_per_week or 32  # Default target
            hours_vs_target = weekly_hours - target_hours

            metrics = StaffFairnessMetrics(
                waiter_id=staff.waiter_id,
                name=staff.name,
                weekly_hours=round(weekly_hours, 1),
                hours_vs_target=round(hours_vs_target, 1),
                prime_shifts_count=prime_shifts,
                prime_shifts_hours=round(prime_hours, 1),
                recent_prime_shift_ratio=0.0,  # Would need historical data
                fairness_score=0.0,  # Calculated below
            )
            staff_metrics.append(metrics)

        # Calculate Gini coefficients
        hours_gini = self._calculate_gini(hours_list)
        prime_gini = self._calculate_gini(prime_hours_list) if any(prime_hours_list) else 0.0

        # Calculate standard deviation of hours
        hours_std = self._calculate_std_dev(hours_list)

        # Identify fairness issues
        issues = []
        if hours_gini > self.GINI_THRESHOLD:
            issues.append(f"Hours distribution is unequal (Gini: {hours_gini:.2f})")

        if prime_gini > self.GINI_THRESHOLD:
            issues.append(f"Prime shift distribution is unequal (Gini: {prime_gini:.2f})")

        if hours_std > self.HOURS_IMBALANCE_THRESHOLD:
            issues.append(f"Hours vary significantly between staff (σ: {hours_std:.1f})")

        # Calculate individual fairness scores
        for metrics in staff_metrics:
            metrics.fairness_score = self._calculate_individual_fairness_score(
                metrics,
                hours_list,
                prime_hours_list,
            )

        return FairnessReport(
            gini_coefficient=round(hours_gini, 3),
            hours_std_dev=round(hours_std, 1),
            prime_shift_gini=round(prime_gini, 3),
            staff_metrics=staff_metrics,
            fairness_issues=issues,
            is_balanced=len(issues) == 0,
        )

    def calculate_assignment_impact(
        self,
        staff: StaffContext,
        new_assignment: ShiftAssignment,
        all_staff: List[StaffContext],
        is_prime_shift: bool = False,
    ) -> float:
        """
        Calculate fairness impact of adding one assignment.

        Returns:
            Impact score from -50 to +50
            - Negative = makes schedule less fair
            - Positive = makes schedule more fair
            - Zero = neutral impact
        """
        if not all_staff:
            return 0.0

        # Calculate current state
        current_hours = [self._calculate_total_hours(s.assigned_shifts) for s in all_staff]
        current_gini = self._calculate_gini(current_hours)
        current_avg = sum(current_hours) / len(current_hours) if current_hours else 0

        # Simulate adding the new assignment
        new_shift_hours = self._calculate_shift_duration(new_assignment)
        staff_index = next(
            (i for i, s in enumerate(all_staff) if s.waiter_id == staff.waiter_id),
            None,
        )

        if staff_index is None:
            return 0.0

        simulated_hours = current_hours.copy()
        simulated_hours[staff_index] += new_shift_hours
        simulated_gini = self._calculate_gini(simulated_hours)

        # Calculate impact based on Gini change
        gini_change = simulated_gini - current_gini

        # Also consider if this brings the staff closer to average
        current_distance = abs(current_hours[staff_index] - current_avg)
        new_distance = abs(simulated_hours[staff_index] - current_avg)
        distance_change = new_distance - current_distance

        # Combine metrics into impact score
        # Gini increase = negative impact
        # Moving away from average = negative impact
        impact = 0.0
        impact -= gini_change * 100  # Scale Gini change
        impact -= distance_change * 2  # Scale distance change

        # Bonus/penalty for prime shifts
        if is_prime_shift:
            # Check if this staff has fewer prime shifts than others
            prime_counts = [
                len([s for s in st.assigned_shifts if self._is_prime_shift_time(s)])
                for st in all_staff
            ]
            staff_prime_count = prime_counts[staff_index]
            avg_prime = sum(prime_counts) / len(prime_counts)

            if staff_prime_count < avg_prime:
                impact += 10  # Bonus for balancing prime shifts
            elif staff_prime_count > avg_prime:
                impact -= 10  # Penalty for hoarding prime shifts

        return max(-50.0, min(50.0, impact))

    def get_underserved_staff(
        self,
        staff_list: List[StaffContext],
        min_hours_threshold: float = 0.0,
    ) -> List[StaffContext]:
        """
        Get staff members who are underserved (fewer hours than they want).

        Args:
            staff_list: List of staff with assignments
            min_hours_threshold: Minimum hours before considering underserved

        Returns:
            List of underserved staff, sorted by how underserved they are
        """
        underserved = []

        for staff in staff_list:
            current_hours = self._calculate_total_hours(staff.assigned_shifts)
            target_hours = staff.min_hours_per_week or 0

            if current_hours < target_hours and current_hours >= min_hours_threshold:
                underserved.append((staff, target_hours - current_hours))

        # Sort by how underserved (most underserved first)
        underserved.sort(key=lambda x: x[1], reverse=True)

        return [s[0] for s in underserved]

    def _calculate_total_hours(self, shifts: List[ShiftAssignment]) -> float:
        """Calculate total hours from a list of shifts."""
        total = 0.0
        for shift in shifts:
            total += self._calculate_shift_duration(shift)
        return total

    def _calculate_shift_duration(self, shift: ShiftAssignment) -> float:
        """Calculate duration of a single shift in hours."""
        start_dt = datetime.combine(shift.shift_date, shift.shift_start)
        end_dt = datetime.combine(shift.shift_date, shift.shift_end)

        if end_dt < start_dt:
            end_dt += timedelta(days=1)

        return (end_dt - start_dt).total_seconds() / 3600

    def _count_prime_shifts(
        self,
        shifts: List[ShiftAssignment],
        prime_slots: List[Tuple[int, time, time]],
    ) -> Tuple[int, float]:
        """Count prime shifts and their total hours."""
        if not prime_slots:
            # Default: Friday/Saturday evening are prime
            prime_slots = [
                (4, time(17, 0), time(23, 0)),  # Friday evening
                (5, time(17, 0), time(23, 0)),  # Saturday evening
            ]

        count = 0
        hours = 0.0

        for shift in shifts:
            day_of_week = shift.shift_date.weekday()
            for prime_day, prime_start, prime_end in prime_slots:
                if day_of_week == prime_day:
                    if self._times_overlap(
                        shift.shift_start, shift.shift_end,
                        prime_start, prime_end,
                    ):
                        count += 1
                        hours += self._calculate_shift_duration(shift)
                        break

        return count, hours

    def _is_prime_shift_time(self, shift: ShiftAssignment) -> bool:
        """Quick check if a shift is during prime time (Fri/Sat evening)."""
        day = shift.shift_date.weekday()
        if day not in (4, 5):  # Friday, Saturday
            return False
        hour = shift.shift_start.hour
        return 17 <= hour <= 23

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

        if e1 < s1:
            e1 += 24 * 60
        if e2 < s2:
            e2 += 24 * 60

        return not (e1 <= s2 or e2 <= s1)

    def _calculate_gini(self, values: List[float]) -> float:
        """
        Calculate Gini coefficient for a list of values.

        Gini = 0 means perfect equality
        Gini = 1 means maximum inequality
        """
        if not values or len(values) < 2:
            return 0.0

        # Filter out zeros for meaningful calculation
        non_zero = [v for v in values if v > 0]
        if not non_zero:
            return 0.0

        sorted_values = sorted(non_zero)
        n = len(sorted_values)
        total = sum(sorted_values)

        if total == 0:
            return 0.0

        # Gini formula
        cumsum = 0.0
        for i, value in enumerate(sorted_values):
            cumsum += (2 * (i + 1) - n - 1) * value

        gini = cumsum / (n * total)
        return max(0.0, min(1.0, gini))

    def _calculate_std_dev(self, values: List[float]) -> float:
        """Calculate standard deviation."""
        if not values or len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5

    def _calculate_individual_fairness_score(
        self,
        metrics: StaffFairnessMetrics,
        all_hours: List[float],
        all_prime_hours: List[float],
    ) -> float:
        """
        Calculate individual fairness score (0-100).

        Higher score = more advantaged (getting more hours/prime shifts)
        Score around 50 = fair/balanced
        """
        if not all_hours:
            return 50.0

        avg_hours = sum(all_hours) / len(all_hours)
        max_hours = max(all_hours) if all_hours else 1.0

        # Hours component (0-50 points)
        if max_hours > 0:
            hours_pct = (metrics.weekly_hours / max_hours) * 50
        else:
            hours_pct = 25

        # Prime shifts component (0-50 points)
        if all_prime_hours and any(all_prime_hours):
            max_prime = max(all_prime_hours)
            if max_prime > 0:
                prime_pct = (metrics.prime_shifts_hours / max_prime) * 50
            else:
                prime_pct = 25
        else:
            prime_pct = 25

        return round(hours_pct + prime_pct, 1)
