"""Service for generating human-readable explanations for schedule assignments."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.services.scheduling_constraints import (
    StaffContext,
    ShiftAssignment,
    StaffingRequirement,
)

logger = logging.getLogger(__name__)


@dataclass
class AssignmentReasoning:
    """Reasoning explanation for a schedule assignment."""

    schedule_item_id: Optional[UUID] = None
    waiter_id: Optional[UUID] = None
    waiter_name: str = ""

    # Core reasons
    reasons: List[str] = field(default_factory=list)

    # Constraint details
    constraint_violations: List[str] = field(default_factory=list)
    preference_matches: List[str] = field(default_factory=list)

    # Fairness context
    fairness_notes: List[str] = field(default_factory=list)

    # Summary
    summary: str = ""
    confidence_score: float = 0.5

    # LLM details (if used)
    llm_enhanced: bool = False
    raw_response: str = ""


class ScheduleReasoningGenerator:
    """
    Generates explanations for schedule assignments.

    Two modes:
    1. Rule-based (fast, deterministic) - default
    2. LLM-enhanced (richer explanations) - optional
    """

    SHIFT_TYPE_NAMES = {
        "morning": "Morning",
        "afternoon": "Afternoon",
        "evening": "Evening",
        "closing": "Closing",
    }

    DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    def __init__(self, call_llm_func: Optional[callable] = None, model: Optional[str] = None):
        """
        Initialize reasoning generator.

        Args:
            call_llm_func: Optional LLM function for enhanced explanations
            model: Model identifier for LLM
        """
        self._call_llm = call_llm_func
        self.model = model or "bytedance-seed/seed-1.6"

    def generate_reasoning(
        self,
        staff: StaffContext,
        assignment: ShiftAssignment,
        requirement: Optional[StaffingRequirement] = None,
        score_breakdown: Optional[Dict[str, float]] = None,
        fairness_impact: float = 0.0,
        use_llm: bool = False,
    ) -> AssignmentReasoning:
        """
        Generate structured reasoning for an assignment.

        Args:
            staff: Staff context with preferences and availability
            assignment: The shift assignment
            requirement: Optional staffing requirement for the slot
            score_breakdown: Optional dict of constraint scores
            fairness_impact: Fairness impact score (-50 to +50)
            use_llm: Whether to use LLM for enhanced explanation

        Returns:
            AssignmentReasoning with explanations
        """
        reasoning = AssignmentReasoning(
            waiter_id=staff.waiter_id,
            waiter_name=staff.name,
        )

        # Generate rule-based reasons
        self._add_availability_reasons(reasoning, staff, assignment)
        self._add_preference_reasons(reasoning, staff, assignment)
        self._add_fairness_reasons(reasoning, staff, fairness_impact)
        self._add_requirement_reasons(reasoning, assignment, requirement)

        # Add score breakdown if provided
        if score_breakdown:
            self._add_score_breakdown_reasons(reasoning, score_breakdown)

        # Generate summary
        reasoning.summary = self._generate_summary(reasoning, staff, assignment)
        reasoning.confidence_score = self._calculate_confidence(reasoning, score_breakdown)

        # Optionally enhance with LLM
        if use_llm and self._call_llm:
            try:
                self._enhance_with_llm(reasoning, staff, assignment, requirement)
            except Exception as e:
                logger.warning(f"LLM enhancement failed: {e}")

        return reasoning

    def generate_batch_reasoning(
        self,
        assignments: List[tuple],  # List of (staff, assignment, requirement, score_breakdown, fairness_impact)
    ) -> List[AssignmentReasoning]:
        """Generate reasoning for multiple assignments."""
        return [
            self.generate_reasoning(
                staff=item[0],
                assignment=item[1],
                requirement=item[2] if len(item) > 2 else None,
                score_breakdown=item[3] if len(item) > 3 else None,
                fairness_impact=item[4] if len(item) > 4 else 0.0,
            )
            for item in assignments
        ]

    def _add_availability_reasons(
        self,
        reasoning: AssignmentReasoning,
        staff: StaffContext,
        assignment: ShiftAssignment,
    ) -> None:
        """Add reasons related to availability."""
        day_name = self.DAY_NAMES[assignment.shift_date.weekday()]

        # Check if this is a preferred time
        is_preferred = False
        for slot in staff.availability_slots:
            if slot.day_of_week == assignment.shift_date.weekday():
                if slot.availability_type == "preferred":
                    if self._time_in_range(assignment.shift_start, slot.start_time, slot.end_time):
                        is_preferred = True
                        reasoning.reasons.append(
                            f"{staff.name} marked {day_name} as a preferred day to work"
                        )
                        reasoning.preference_matches.append("Preferred day")
                        break

        if not is_preferred:
            reasoning.reasons.append(f"{staff.name} is available on {day_name}")

    def _add_preference_reasons(
        self,
        reasoning: AssignmentReasoning,
        staff: StaffContext,
        assignment: ShiftAssignment,
    ) -> None:
        """Add reasons related to staff preferences."""
        # Role preference
        if staff.preferred_roles and assignment.role in staff.preferred_roles:
            reasoning.reasons.append(f"Role '{assignment.role}' is one of their preferred roles")
            reasoning.preference_matches.append(f"Preferred role: {assignment.role}")

        # Shift type preference
        shift_type = self._get_shift_type(assignment.shift_start)
        shift_type_name = self.SHIFT_TYPE_NAMES.get(shift_type, shift_type)

        if staff.preferred_shift_types and shift_type in staff.preferred_shift_types:
            reasoning.reasons.append(f"{shift_type_name} shifts are preferred")
            reasoning.preference_matches.append(f"Preferred shift: {shift_type_name}")

        # Section preference
        if assignment.section_id and staff.preferred_sections:
            if assignment.section_id in staff.preferred_sections:
                reasoning.reasons.append("Assigned to a preferred section")
                reasoning.preference_matches.append("Preferred section")

        # Check for soft violations
        if staff.avoid_clopening and self._is_clopening_risk(staff, assignment):
            reasoning.constraint_violations.append(
                "Short gap between shifts (clopening warning)"
            )

    def _add_fairness_reasons(
        self,
        reasoning: AssignmentReasoning,
        staff: StaffContext,
        fairness_impact: float,
    ) -> None:
        """Add reasons related to fairness."""
        if fairness_impact > 10:
            reasoning.fairness_notes.append("Helps balance hours across staff")
            reasoning.reasons.append("Assignment improves overall schedule fairness")
        elif fairness_impact > 0:
            reasoning.fairness_notes.append("Good fit for current schedule balance")
        elif fairness_impact < -10:
            reasoning.fairness_notes.append("May create slight hours imbalance")

        # Check hours context
        current_hours = sum(
            self._calculate_shift_hours(s) for s in staff.assigned_shifts
        )

        if staff.min_hours_per_week and current_hours < staff.min_hours_per_week:
            hours_needed = staff.min_hours_per_week - current_hours
            reasoning.fairness_notes.append(
                f"Needs ~{hours_needed:.0f} more hours to meet minimum"
            )

    def _add_requirement_reasons(
        self,
        reasoning: AssignmentReasoning,
        assignment: ShiftAssignment,
        requirement: Optional[StaffingRequirement],
    ) -> None:
        """Add reasons related to staffing requirements."""
        if not requirement:
            return

        if requirement.is_prime_shift:
            reasoning.reasons.append("This is a prime/high-demand time slot")

        # Format time nicely
        start_str = assignment.shift_start.strftime("%I:%M %p").lstrip("0")
        end_str = assignment.shift_end.strftime("%I:%M %p").lstrip("0")
        reasoning.reasons.append(
            f"Coverage needed from {start_str} to {end_str}"
        )

    def _add_score_breakdown_reasons(
        self,
        reasoning: AssignmentReasoning,
        breakdown: Dict[str, float],
    ) -> None:
        """Add reasons from constraint score breakdown."""
        for key, value in breakdown.items():
            if value > 5:
                if key == "preference_match":
                    pass  # Already covered in preference reasons
                elif key == "section_preference":
                    if "Preferred section" not in reasoning.preference_matches:
                        reasoning.preference_matches.append("Section preference matched")
                elif key == "preferred_availability":
                    if "Preferred day" not in reasoning.preference_matches:
                        reasoning.preference_matches.append("Preferred availability matched")
            elif value < -5:
                if key == "clopening_penalty":
                    if "clopening" not in str(reasoning.constraint_violations):
                        reasoning.constraint_violations.append(
                            "Close-open pattern detected"
                        )

    def _generate_summary(
        self,
        reasoning: AssignmentReasoning,
        staff: StaffContext,
        assignment: ShiftAssignment,
    ) -> str:
        """Generate a human-readable summary."""
        day_name = self.DAY_NAMES[assignment.shift_date.weekday()]
        shift_type = self._get_shift_type(assignment.shift_start)

        # Build summary based on available info
        parts = []

        if reasoning.preference_matches:
            match_count = len(reasoning.preference_matches)
            if match_count >= 2:
                parts.append(f"Excellent fit with {match_count} preference matches")
            else:
                parts.append(f"Good fit with preference match")

        if reasoning.fairness_notes and "balance" in str(reasoning.fairness_notes).lower():
            parts.append("helps maintain fair distribution")

        if reasoning.constraint_violations:
            parts.append(f"note: {len(reasoning.constraint_violations)} soft constraint warning(s)")

        if parts:
            return f"{staff.name} assigned to {day_name} {shift_type} shift - " + "; ".join(parts) + "."
        else:
            return f"{staff.name} assigned to {day_name} {shift_type} shift based on availability."

    def _calculate_confidence(
        self,
        reasoning: AssignmentReasoning,
        score_breakdown: Optional[Dict[str, float]],
    ) -> float:
        """Calculate confidence score for the assignment."""
        confidence = 0.5  # Base

        # Boost for preference matches
        confidence += len(reasoning.preference_matches) * 0.1

        # Boost for positive fairness
        if reasoning.fairness_notes:
            if "balance" in str(reasoning.fairness_notes).lower():
                confidence += 0.1

        # Penalty for violations
        confidence -= len(reasoning.constraint_violations) * 0.1

        # Use score breakdown if available
        if score_breakdown:
            avg_score = sum(score_breakdown.values()) / max(len(score_breakdown), 1)
            if avg_score > 10:
                confidence += 0.1
            elif avg_score < -10:
                confidence -= 0.1

        return max(0.1, min(0.95, confidence))

    async def _enhance_with_llm(
        self,
        reasoning: AssignmentReasoning,
        staff: StaffContext,
        assignment: ShiftAssignment,
        requirement: Optional[StaffingRequirement],
    ) -> None:
        """Enhance reasoning with LLM-generated explanations."""
        prompt = self._build_llm_prompt(reasoning, staff, assignment, requirement)

        try:
            response = await self._call_llm(
                model=self.model,
                prompt=prompt,
                max_tokens=500,
                temperature=0.3,
            )

            reasoning.raw_response = response
            reasoning.llm_enhanced = True

            # Try to parse enhanced summary
            if response:
                # Look for a summary in the response
                lines = response.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if len(line) > 30 and not line.startswith('{'):
                        reasoning.summary = line[:500]
                        break

        except Exception as e:
            logger.warning(f"LLM enhancement failed: {e}")

    def _build_llm_prompt(
        self,
        reasoning: AssignmentReasoning,
        staff: StaffContext,
        assignment: ShiftAssignment,
        requirement: Optional[StaffingRequirement],
    ) -> str:
        """Build prompt for LLM enhancement."""
        day_name = self.DAY_NAMES[assignment.shift_date.weekday()]

        return f"""Summarize why this schedule assignment is a good choice in 1-2 sentences.

Staff: {staff.name}
Shift: {day_name}, {assignment.shift_start.strftime('%I:%M %p')} - {assignment.shift_end.strftime('%I:%M %p')}
Role: {assignment.role}

Reasons identified:
{chr(10).join('- ' + r for r in reasoning.reasons[:5])}

Preference matches: {', '.join(reasoning.preference_matches) if reasoning.preference_matches else 'None'}
Concerns: {', '.join(reasoning.constraint_violations) if reasoning.constraint_violations else 'None'}

Write a brief, professional summary explaining this assignment choice."""

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

    def _time_in_range(self, check_time: time, start: time, end: time) -> bool:
        """Check if a time is within a range."""
        def to_minutes(t: time) -> int:
            return t.hour * 60 + t.minute

        check = to_minutes(check_time)
        s = to_minutes(start)
        e = to_minutes(end)

        if e < s:  # Overnight
            return check >= s or check <= e
        return s <= check <= e

    def _is_clopening_risk(self, staff: StaffContext, assignment: ShiftAssignment) -> bool:
        """Check if assignment creates a clopening pattern."""
        from datetime import datetime, timedelta

        for existing in staff.assigned_shifts:
            # Check if same day or consecutive days
            day_diff = abs((assignment.shift_date - existing.shift_date).days)
            if day_diff > 1:
                continue

            # Calculate gap between shifts
            if day_diff == 0:
                continue  # Same day, not clopening

            # Check time gap
            if assignment.shift_date > existing.shift_date:
                # New shift is after existing
                end_dt = datetime.combine(existing.shift_date, existing.shift_end)
                start_dt = datetime.combine(assignment.shift_date, assignment.shift_start)
            else:
                # New shift is before existing
                end_dt = datetime.combine(assignment.shift_date, assignment.shift_end)
                start_dt = datetime.combine(existing.shift_date, existing.shift_start)

            gap_hours = (start_dt - end_dt).total_seconds() / 3600
            if gap_hours < 10:  # Less than 10 hours between shifts
                return True

        return False

    def _calculate_shift_hours(self, shift: ShiftAssignment) -> float:
        """Calculate hours for a shift."""
        from datetime import datetime, timedelta

        start_dt = datetime.combine(shift.shift_date, shift.shift_start)
        end_dt = datetime.combine(shift.shift_date, shift.shift_end)
        if end_dt < start_dt:
            end_dt += timedelta(days=1)
        return (end_dt - start_dt).total_seconds() / 3600
