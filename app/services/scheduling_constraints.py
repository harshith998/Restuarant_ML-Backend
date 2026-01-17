"""Service for validating scheduling constraints."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Set
from uuid import UUID


@dataclass
class StaffContext:
    """Context for a staff member during scheduling."""

    waiter_id: UUID
    name: str
    role: str
    is_active: bool

    # Availability for the week
    availability_slots: List["AvailabilitySlot"] = field(default_factory=list)

    # Preferences
    preferred_roles: List[str] = field(default_factory=list)
    preferred_shift_types: List[str] = field(default_factory=list)
    preferred_sections: List[UUID] = field(default_factory=list)
    max_shifts_per_week: Optional[int] = None
    max_hours_per_week: Optional[int] = None
    min_hours_per_week: Optional[int] = None
    avoid_clopening: bool = True

    # Current assignments this week
    assigned_shifts: List["ShiftAssignment"] = field(default_factory=list)


@dataclass
class AvailabilitySlot:
    """A single availability window for a staff member."""

    day_of_week: int  # 0=Monday
    start_time: time
    end_time: time
    availability_type: str  # available, unavailable, preferred


@dataclass
class ShiftAssignment:
    """A shift assignment for tracking purposes."""

    waiter_id: Optional[UUID]
    shift_date: date
    shift_start: time
    shift_end: time
    role: str
    section_id: Optional[UUID] = None


@dataclass
class SchedulingContext:
    """Full context for a scheduling decision."""

    restaurant_id: UUID
    week_start: date
    staff: List[StaffContext]
    staffing_requirements: List["StaffingRequirement"]


@dataclass
class StaffingRequirement:
    """A staffing requirement for a time slot."""

    day_of_week: int
    start_time: time
    end_time: time
    role: str
    min_staff: int
    max_staff: Optional[int]
    is_prime_shift: bool = False


@dataclass
class ConstraintViolation:
    """A constraint violation."""

    constraint_type: str  # hard or soft
    constraint_name: str
    message: str
    severity: int = 1  # 1-10, higher = more severe


class ConstraintValidator:
    """
    Validates schedule assignments against hard and soft constraints.

    Hard constraints (must be satisfied):
    - Staff available at assigned time
    - Role matches staff capabilities
    - Max hours not exceeded
    - No overlapping shifts
    - Staff is active

    Soft constraints (scored, can be violated):
    - Preference matching
    - Clopening penalty
    - Section preference
    - Min hours met
    """

    # Minimum hours between shifts to avoid "clopening"
    CLOPENING_MIN_HOURS = 10

    # Hours that define shift types
    SHIFT_TYPE_HOURS = {
        "morning": (6, 11),
        "afternoon": (11, 16),
        "evening": (16, 21),
        "closing": (21, 2),  # Wraps around midnight
    }

    def validate_hard_constraints(
        self,
        staff: StaffContext,
        assignment: ShiftAssignment,
        context: SchedulingContext,
    ) -> List[ConstraintViolation]:
        """
        Validate hard constraints for an assignment.

        Returns:
            List of violations (empty = valid)
        """
        violations = []

        # Check staff is active
        if not staff.is_active:
            violations.append(ConstraintViolation(
                constraint_type="hard",
                constraint_name="staff_active",
                message=f"{staff.name} is not currently active",
                severity=10,
            ))

        # Check availability
        if not self._is_available(staff, assignment):
            violations.append(ConstraintViolation(
                constraint_type="hard",
                constraint_name="availability",
                message=f"{staff.name} is not available for this time slot",
                severity=10,
            ))

        # Check for overlapping shifts
        overlap = self._has_overlapping_shift(staff, assignment)
        if overlap:
            violations.append(ConstraintViolation(
                constraint_type="hard",
                constraint_name="no_overlap",
                message=f"{staff.name} already has a shift that overlaps with this time",
                severity=10,
            ))

        # Check max hours
        if staff.max_hours_per_week is not None:
            current_hours = self._calculate_weekly_hours(staff)
            new_hours = self._calculate_shift_hours(assignment)
            if current_hours + new_hours > staff.max_hours_per_week:
                violations.append(ConstraintViolation(
                    constraint_type="hard",
                    constraint_name="max_hours",
                    message=f"{staff.name} would exceed {staff.max_hours_per_week} hours/week",
                    severity=9,
                ))

        # Check max shifts
        if staff.max_shifts_per_week is not None:
            current_shifts = len(staff.assigned_shifts)
            if current_shifts >= staff.max_shifts_per_week:
                violations.append(ConstraintViolation(
                    constraint_type="hard",
                    constraint_name="max_shifts",
                    message=f"{staff.name} would exceed {staff.max_shifts_per_week} shifts/week",
                    severity=9,
                ))

        return violations

    def score_soft_constraints(
        self,
        staff: StaffContext,
        assignment: ShiftAssignment,
        context: SchedulingContext,
    ) -> float:
        """
        Calculate a score for soft constraint satisfaction.

        Returns:
            Score 0-100 where higher is better
        """
        score = 50.0  # Start at neutral

        # Preference matching
        score += self._score_preference_match(staff, assignment)

        # Clopening penalty
        score += self._score_clopening(staff, assignment)

        # Section preference
        score += self._score_section_preference(staff, assignment)

        # Shift type preference
        score += self._score_shift_type_preference(staff, assignment)

        # Preferred availability bonus
        score += self._score_preferred_availability(staff, assignment)

        # Clamp to 0-100
        return max(0.0, min(100.0, score))

    def get_soft_constraint_breakdown(
        self,
        staff: StaffContext,
        assignment: ShiftAssignment,
        context: SchedulingContext,
    ) -> Dict[str, float]:
        """Get individual soft constraint scores for debugging/explanation."""
        return {
            "preference_match": self._score_preference_match(staff, assignment),
            "clopening_penalty": self._score_clopening(staff, assignment),
            "section_preference": self._score_section_preference(staff, assignment),
            "shift_type_preference": self._score_shift_type_preference(staff, assignment),
            "preferred_availability": self._score_preferred_availability(staff, assignment),
        }

    def _is_available(
        self,
        staff: StaffContext,
        assignment: ShiftAssignment,
    ) -> bool:
        """Check if staff is available for the assignment time."""
        day_of_week = assignment.shift_date.weekday()

        for slot in staff.availability_slots:
            if slot.day_of_week != day_of_week:
                continue

            if slot.availability_type == "unavailable":
                # Check if assignment overlaps with unavailable slot
                if self._times_overlap(
                    assignment.shift_start, assignment.shift_end,
                    slot.start_time, slot.end_time,
                ):
                    return False
            elif slot.availability_type in ("available", "preferred"):
                # Check if assignment is within available slot
                if self._time_within(
                    assignment.shift_start, assignment.shift_end,
                    slot.start_time, slot.end_time,
                ):
                    return True

        # No matching availability found - default to unavailable
        return False

    def _has_overlapping_shift(
        self,
        staff: StaffContext,
        assignment: ShiftAssignment,
    ) -> bool:
        """Check if the new assignment overlaps with existing shifts."""
        for existing in staff.assigned_shifts:
            if existing.shift_date != assignment.shift_date:
                continue

            if self._times_overlap(
                assignment.shift_start, assignment.shift_end,
                existing.shift_start, existing.shift_end,
            ):
                return True

        return False

    def _calculate_weekly_hours(self, staff: StaffContext) -> float:
        """Calculate total hours already assigned this week."""
        total = 0.0
        for shift in staff.assigned_shifts:
            total += self._calculate_shift_hours(shift)
        return total

    def _calculate_shift_hours(self, assignment: ShiftAssignment) -> float:
        """Calculate hours for a single shift."""
        start_dt = datetime.combine(assignment.shift_date, assignment.shift_start)
        end_dt = datetime.combine(assignment.shift_date, assignment.shift_end)

        # Handle overnight shifts
        if end_dt < start_dt:
            end_dt += timedelta(days=1)

        return (end_dt - start_dt).total_seconds() / 3600

    def _score_preference_match(
        self,
        staff: StaffContext,
        assignment: ShiftAssignment,
    ) -> float:
        """Score based on role preference matching."""
        if not staff.preferred_roles:
            return 0.0

        if assignment.role in staff.preferred_roles:
            return 15.0  # Bonus for preferred role

        return -5.0  # Penalty for non-preferred role

    def _score_clopening(
        self,
        staff: StaffContext,
        assignment: ShiftAssignment,
    ) -> float:
        """Score penalty for clopening (close-open pattern)."""
        if not staff.avoid_clopening:
            return 0.0

        for existing in staff.assigned_shifts:
            hours_gap = self._calculate_gap_hours(existing, assignment)
            if hours_gap is not None and hours_gap < self.CLOPENING_MIN_HOURS:
                # Penalty proportional to how short the gap is
                penalty = (self.CLOPENING_MIN_HOURS - hours_gap) * 2.5
                return -min(25.0, penalty)

        return 0.0

    def _score_section_preference(
        self,
        staff: StaffContext,
        assignment: ShiftAssignment,
    ) -> float:
        """Score based on section preference."""
        if not staff.preferred_sections or not assignment.section_id:
            return 0.0

        if assignment.section_id in staff.preferred_sections:
            return 10.0

        return 0.0

    def _score_shift_type_preference(
        self,
        staff: StaffContext,
        assignment: ShiftAssignment,
    ) -> float:
        """Score based on shift type (morning/evening/etc) preference."""
        if not staff.preferred_shift_types:
            return 0.0

        shift_type = self._get_shift_type(assignment.shift_start)
        if shift_type in staff.preferred_shift_types:
            return 10.0

        return -5.0

    def _score_preferred_availability(
        self,
        staff: StaffContext,
        assignment: ShiftAssignment,
    ) -> float:
        """Bonus for assigning during preferred (not just available) times."""
        day_of_week = assignment.shift_date.weekday()

        for slot in staff.availability_slots:
            if slot.day_of_week != day_of_week:
                continue

            if slot.availability_type == "preferred":
                if self._time_within(
                    assignment.shift_start, assignment.shift_end,
                    slot.start_time, slot.end_time,
                ):
                    return 10.0

        return 0.0

    def _times_overlap(
        self,
        start1: time,
        end1: time,
        start2: time,
        end2: time,
    ) -> bool:
        """Check if two time ranges overlap."""
        # Convert to minutes for easier comparison
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

    def _time_within(
        self,
        inner_start: time,
        inner_end: time,
        outer_start: time,
        outer_end: time,
    ) -> bool:
        """Check if inner time range is within outer time range."""
        def to_minutes(t: time) -> int:
            return t.hour * 60 + t.minute

        is_, ie = to_minutes(inner_start), to_minutes(inner_end)
        os_, oe = to_minutes(outer_start), to_minutes(outer_end)

        # Handle overnight
        if ie < is_:
            ie += 24 * 60
        if oe < os_:
            oe += 24 * 60

        return os_ <= is_ and ie <= oe

    def _calculate_gap_hours(
        self,
        shift1: ShiftAssignment,
        shift2: ShiftAssignment,
    ) -> Optional[float]:
        """Calculate hours between end of shift1 and start of shift2."""
        # Determine which shift is first
        dt1_end = datetime.combine(shift1.shift_date, shift1.shift_end)
        dt2_start = datetime.combine(shift2.shift_date, shift2.shift_start)

        # Handle overnight shifts
        if shift1.shift_end < shift1.shift_start:
            dt1_end += timedelta(days=1)

        # Check if shifts are on consecutive days
        day_diff = (shift2.shift_date - shift1.shift_date).days
        if day_diff < 0:
            # Swap - shift2 is actually before shift1
            dt1_end = datetime.combine(shift2.shift_date, shift2.shift_end)
            dt2_start = datetime.combine(shift1.shift_date, shift1.shift_start)
            if shift2.shift_end < shift2.shift_start:
                dt1_end += timedelta(days=1)
            day_diff = -day_diff

        if day_diff > 1:
            return None  # Not consecutive, no clopening concern

        gap = (dt2_start - dt1_end).total_seconds() / 3600
        if gap < 0:
            gap += 24  # Next day

        return gap

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
