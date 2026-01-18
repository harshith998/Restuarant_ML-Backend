"""Main scheduling engine that orchestrates schedule generation."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Waiter,
    StaffAvailability,
    StaffPreference,
    Schedule,
    ScheduleItem,
    ScheduleRun,
    ScheduleReasoning,
    StaffingRequirements,
)
from app.services.demand_forecaster import DemandForecaster, WeeklyForecast
from app.services.scheduling_constraints import (
    ConstraintValidator,
    StaffContext,
    AvailabilitySlot,
    ShiftAssignment,
    SchedulingContext,
    StaffingRequirement,
)
from app.services.fairness_calculator import FairnessCalculator, FairnessReport
from app.services.llm_client import call_llm, LLMError


ENGINE_VERSION = "1.0.0"

SCHEDULE_SUMMARY_SYSTEM_PROMPT = """You are an AI scheduling assistant explaining scheduling decisions.

Write a concise, conversational 3-4 sentence explanation for a restaurant manager.
Focus on coverage, fairness, preferences, and trade-offs. Be specific and actionable."""

logger = logging.getLogger(__name__)


@dataclass
class CandidateScore:
    """Score for a candidate assignment."""

    staff: StaffContext
    assignment: ShiftAssignment
    constraint_score: float  # 0-100 from soft constraints
    fairness_impact: float  # -50 to +50
    total_score: float  # Combined score

    # Score breakdown for reasoning
    breakdown: Dict[str, float] = field(default_factory=dict)


@dataclass
class EngineResult:
    """Result from a scheduling engine run."""

    schedule_run_id: UUID
    schedule_id: UUID
    status: str  # completed, failed
    items_created: int
    total_hours_scheduled: float
    fairness_report: Optional[FairnessReport]
    error_message: Optional[str] = None

    # Summary metrics
    coverage_pct: float = 0.0  # % of required slots filled
    preference_match_avg: float = 0.0  # Avg preference score


class SchedulingEngine:
    """
    Main orchestrator for schedule generation using score-and-rank algorithm.

    Algorithm:
    1. Gather inputs (staff, availability, preferences, requirements)
    2. Generate demand forecast
    3. For each time slot needing coverage:
       a. Find all available staff
       b. Score each candidate (constraints + preferences + fairness)
       c. Assign top-scored candidate
    4. Generate reasoning for each assignment
    5. Compute final fairness scores
    """

    # Scoring weights
    CONSTRAINT_WEIGHT = 0.5
    FAIRNESS_WEIGHT = 0.3
    PREFERENCE_BONUS_WEIGHT = 0.2

    def __init__(self, session: AsyncSession):
        self.session = session
        self.forecaster = DemandForecaster(session)
        self.constraints = ConstraintValidator()
        self.fairness = FairnessCalculator()

    async def run(
        self,
        restaurant_id: UUID,
        week_start: date,
        run_id: Optional[UUID] = None,
    ) -> EngineResult:
        """
        Execute a scheduling run for a week.

        Args:
            restaurant_id: The restaurant to schedule
            week_start: Monday of the week to schedule
            run_id: Optional existing ScheduleRun ID to update

        Returns:
            EngineResult with created schedule and metrics
        """
        # Get or create the run record
        schedule_run = await self._get_or_create_run(restaurant_id, week_start, run_id)

        try:
            # Update status to running
            schedule_run.run_status = "running"
            schedule_run.started_at = datetime.utcnow()
            await self.session.commit()

            # Gather all inputs
            staff_list = await self._load_staff_context(restaurant_id, week_start)
            requirements = await self._load_staffing_requirements(restaurant_id)
            forecast = await self.forecaster.forecast_week(restaurant_id, week_start)

            # Store input snapshot
            schedule_run.inputs_snapshot = {
                "staff_count": len(staff_list),
                "requirements_count": len(requirements),
                "forecast_trend": forecast.overall_trend,
                "forecast_total_covers": forecast.total_predicted_covers,
            }

            # Create scheduling context
            context = SchedulingContext(
                restaurant_id=restaurant_id,
                week_start=week_start,
                staff=staff_list,
                staffing_requirements=[
                    StaffingRequirement(
                        day_of_week=r.day_of_week,
                        start_time=r.start_time,
                        end_time=r.end_time,
                        role=r.role,
                        min_staff=r.min_staff,
                        max_staff=r.max_staff,
                        is_prime_shift=r.is_prime_shift,
                    )
                    for r in requirements
                ],
            )

            # Create the schedule
            schedule = await self._create_schedule(restaurant_id, week_start, schedule_run.id)

            # Generate assignments for each time slot
            items_created = 0
            total_hours = 0.0
            slots_filled = 0
            slots_required = 0
            preference_scores = []
            gaps: List[str] = []

            for day_offset in range(7):
                current_date = week_start + timedelta(days=day_offset)
                day_of_week = current_date.weekday()

                # Get requirements for this day
                day_requirements = [r for r in context.staffing_requirements if r.day_of_week == day_of_week]

                for req in day_requirements:
                    slots_required += req.min_staff

                    # Find available candidates
                    candidates = self._find_available_candidates(
                        staff_list,
                        current_date,
                        req.start_time,
                        req.end_time,
                        req.role,
                        context,
                    )

                    # Assign up to min_staff (or max_staff if specified)
                    target_count = req.min_staff
                    assigned_count = 0

                    for candidate in candidates:
                        if assigned_count >= target_count:
                            break

                        # Create the assignment
                        assignment = candidate.assignment
                        item = await self._create_schedule_item(
                            schedule.id,
                            assignment,
                            candidate.constraint_score,
                            candidate.fairness_impact,
                        )

                        # Create reasoning
                        await self._create_reasoning(
                            schedule_run.id,
                            item.id,
                            candidate,
                            req,
                        )

                        # Update staff context
                        self._add_assignment_to_context(staff_list, candidate.staff.waiter_id, assignment)

                        items_created += 1
                        assigned_count += 1
                        slots_filled += 1
                        total_hours += self._calculate_hours(assignment)
                        preference_scores.append(candidate.constraint_score)

                    if assigned_count < target_count:
                        gap_count = target_count - assigned_count
                        gaps.append(
                            f"{current_date.strftime('%a')} {req.start_time}-{req.end_time} "
                            f"{req.role} short {gap_count}"
                        )

            # Calculate final fairness
            fairness_report = self.fairness.calculate_schedule_fairness(staff_list)

            # Calculate coverage
            coverage_pct = (slots_filled / slots_required * 100) if slots_required > 0 else 100.0

            # Always attempt LLM summary generation (store None on failure)
            summary_prompt = f"""
You are an AI scheduling assistant explaining your scheduling decisions to a restaurant manager.

Schedule created for week of {week_start}:
- Created {items_created} shifts totaling {round(total_hours, 1)} hours
- Achieved {round(coverage_pct, 1)}% coverage of staffing requirements
- Fairness score (Gini coefficient): {fairness_report.gini_coefficient:.2f} (lower is more fair)
- Preference matching: {round(sum(preference_scores) / len(preference_scores), 1) if preference_scores else 0}% of shifts matched staff preferences
- {len(gaps)} coverage gaps remaining

Staff context:
- {len(staff_list)} total staff members
- {len(requirements)} different time slot requirements
- Mix of full-time and part-time availability

Write a natural, conversational 3-4 sentence explanation of your scheduling strategy. Explain:
- What you prioritized (fairness, coverage, preferences, peak periods)
- Key decisions you made (who got which shifts and why)
- Any trade-offs or compromises (why some gaps exist, which preferences couldn't be met)
- Actionable suggestions (hire more staff, adjust availability, etc.)

Respond with JSON: {{"summary": "<your explanation>"}}
"""

            try:
                response = await call_llm(
                    system_prompt=SCHEDULE_SUMMARY_SYSTEM_PROMPT,
                    user_prompt=summary_prompt,
                    temperature=0.5,
                    max_tokens=500,
                    response_format="json",
                )
                schedule.schedule_summary = response.get("summary")
            except LLMError as e:
                logger.error(f"LLM schedule summary failed: {e}")
                schedule.schedule_summary = None
            except Exception as e:
                logger.error(f"LLM schedule summary failed unexpectedly: {e}")
                schedule.schedule_summary = None

            # Update run with success
            schedule_run.run_status = "completed"
            schedule_run.completed_at = datetime.utcnow()
            schedule_run.summary_metrics = {
                "items_created": items_created,
                "total_hours": round(total_hours, 1),
                "coverage_pct": round(coverage_pct, 1),
                "fairness_gini": fairness_report.gini_coefficient,
                "preference_avg": round(sum(preference_scores) / len(preference_scores), 1) if preference_scores else 0,
            }
            await self.session.commit()

            return EngineResult(
                schedule_run_id=schedule_run.id,
                schedule_id=schedule.id,
                status="completed",
                items_created=items_created,
                total_hours_scheduled=round(total_hours, 1),
                fairness_report=fairness_report,
                coverage_pct=round(coverage_pct, 1),
                preference_match_avg=round(sum(preference_scores) / len(preference_scores), 1) if preference_scores else 0,
            )

        except Exception as e:
            schedule_run.run_status = "failed"
            schedule_run.error_message = str(e)
            schedule_run.completed_at = datetime.utcnow()
            await self.session.commit()

            return EngineResult(
                schedule_run_id=schedule_run.id,
                schedule_id=UUID(int=0),  # Placeholder
                status="failed",
                items_created=0,
                total_hours_scheduled=0.0,
                fairness_report=None,
                error_message=str(e),
            )

    async def _get_or_create_run(
        self,
        restaurant_id: UUID,
        week_start: date,
        run_id: Optional[UUID],
    ) -> ScheduleRun:
        """Get existing run or create a new one."""
        if run_id:
            run = await self.session.get(ScheduleRun, run_id)
            if run:
                return run

        run = ScheduleRun(
            restaurant_id=restaurant_id,
            week_start_date=week_start,
            engine_version=ENGINE_VERSION,
            run_status="pending",
        )
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def _load_staff_context(
        self,
        restaurant_id: UUID,
        week_start: date,
    ) -> List[StaffContext]:
        """Load staff with their availability and preferences."""
        # Get active waiters
        stmt = (
            select(Waiter)
            .where(Waiter.restaurant_id == restaurant_id)
            .where(Waiter.is_active == True)  # noqa: E712
        )
        result = await self.session.execute(stmt)
        waiters = result.scalars().all()

        staff_list = []
        for waiter in waiters:
            # Load availability
            avail_stmt = (
                select(StaffAvailability)
                .where(StaffAvailability.waiter_id == waiter.id)
            )
            avail_result = await self.session.execute(avail_stmt)
            availabilities = avail_result.scalars().all()

            # Load preferences
            pref_stmt = (
                select(StaffPreference)
                .where(StaffPreference.waiter_id == waiter.id)
            )
            pref_result = await self.session.execute(pref_stmt)
            preferences = pref_result.scalar_one_or_none()

            # Build context
            context = StaffContext(
                waiter_id=waiter.id,
                name=waiter.name,
                role=waiter.role,
                is_active=waiter.is_active,
                availability_slots=[
                    AvailabilitySlot(
                        day_of_week=a.day_of_week,
                        start_time=a.start_time,
                        end_time=a.end_time,
                        availability_type=a.availability_type,
                    )
                    for a in availabilities
                    if a.is_effective_on(week_start)
                ],
                preferred_roles=preferences.preferred_roles if preferences else [],
                preferred_shift_types=preferences.preferred_shift_types if preferences else [],
                preferred_sections=[UUID(s) for s in (preferences.preferred_sections or [])] if preferences else [],
                max_shifts_per_week=preferences.max_shifts_per_week if preferences else None,
                max_hours_per_week=preferences.max_hours_per_week if preferences else None,
                min_hours_per_week=preferences.min_hours_per_week if preferences else None,
                avoid_clopening=preferences.avoid_clopening if preferences else True,
            )
            staff_list.append(context)

        return staff_list

    async def _load_staffing_requirements(
        self,
        restaurant_id: UUID,
    ) -> List[StaffingRequirements]:
        """Load staffing requirements for the restaurant."""
        stmt = (
            select(StaffingRequirements)
            .where(StaffingRequirements.restaurant_id == restaurant_id)
            .order_by(StaffingRequirements.day_of_week, StaffingRequirements.start_time)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _create_schedule(
        self,
        restaurant_id: UUID,
        week_start: date,
        run_id: UUID,
    ) -> Schedule:
        """Create a new schedule for the week."""
        # Always create a new version for the same week (allows repeated runs)
        existing_stmt = (
            select(Schedule)
            .where(
                Schedule.restaurant_id == restaurant_id,
                Schedule.week_start_date == week_start,
            )
            .order_by(Schedule.version.desc())
            .limit(1)
        )
        existing_result = await self.session.execute(existing_stmt)
        latest_schedule = existing_result.scalar_one_or_none()
        next_version = (latest_schedule.version + 1) if latest_schedule else 1

        schedule = Schedule(
            restaurant_id=restaurant_id,
            week_start_date=week_start,
            status="draft",
            generated_by="engine",
            version=next_version,
            schedule_run_id=run_id,
        )
        self.session.add(schedule)
        await self.session.commit()
        await self.session.refresh(schedule)
        return schedule

    def _find_available_candidates(
        self,
        staff_list: List[StaffContext],
        shift_date: date,
        start_time: time,
        end_time: time,
        role: str,
        context: SchedulingContext,
    ) -> List[CandidateScore]:
        """
        Find and score all available candidates for a slot.

        Returns candidates sorted by total score (highest first).
        """
        candidates = []

        for staff in staff_list:
            assignment = ShiftAssignment(
                waiter_id=staff.waiter_id,
                shift_date=shift_date,
                shift_start=start_time,
                shift_end=end_time,
                role=role,
            )

            # Check hard constraints
            violations = self.constraints.validate_hard_constraints(staff, assignment, context)
            if violations:
                continue  # Skip candidates with hard constraint violations

            # Score soft constraints
            constraint_score = self.constraints.score_soft_constraints(staff, assignment, context)
            breakdown = self.constraints.get_soft_constraint_breakdown(staff, assignment, context)

            # Calculate fairness impact
            fairness_impact = self.fairness.calculate_assignment_impact(
                staff,
                assignment,
                staff_list,
                is_prime_shift=self._is_prime_slot(shift_date, start_time),
            )

            # Calculate total score
            total_score = (
                constraint_score * self.CONSTRAINT_WEIGHT +
                (fairness_impact + 50) * self.FAIRNESS_WEIGHT +  # Normalize -50..50 to 0..100
                (constraint_score * self.PREFERENCE_BONUS_WEIGHT)
            )

            candidates.append(CandidateScore(
                staff=staff,
                assignment=assignment,
                constraint_score=constraint_score,
                fairness_impact=fairness_impact,
                total_score=total_score,
                breakdown=breakdown,
            ))

        # Sort by total score descending
        candidates.sort(key=lambda c: c.total_score, reverse=True)
        return candidates

    def _is_prime_slot(self, shift_date: date, start_time: time) -> bool:
        """Check if a slot is a prime (desirable) shift."""
        day = shift_date.weekday()
        hour = start_time.hour
        return day in (4, 5) and 17 <= hour <= 21  # Fri/Sat evening

    async def _create_schedule_item(
        self,
        schedule_id: UUID,
        assignment: ShiftAssignment,
        preference_score: float,
        fairness_impact: float,
    ) -> ScheduleItem:
        """Create a schedule item from an assignment."""
        item = ScheduleItem(
            schedule_id=schedule_id,
            waiter_id=assignment.waiter_id,
            role=assignment.role,
            section_id=assignment.section_id,
            shift_date=assignment.shift_date,
            shift_start=assignment.shift_start,
            shift_end=assignment.shift_end,
            source="engine",
            preference_match_score=round(preference_score, 2),
            fairness_impact_score=round(fairness_impact, 2),
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def _create_reasoning(
        self,
        run_id: UUID,
        item_id: UUID,
        candidate: CandidateScore,
        requirement: StaffingRequirement,
    ) -> ScheduleReasoning:
        """Create reasoning record for an assignment."""
        reasons = []

        # Build reasoning from breakdown
        if candidate.breakdown.get("preference_match", 0) > 0:
            reasons.append(f"Role {candidate.assignment.role} is a preferred role")
        if candidate.breakdown.get("preferred_availability", 0) > 0:
            reasons.append("Staff marked this as a preferred time to work")
        if candidate.breakdown.get("shift_type_preference", 0) > 0:
            reasons.append("Shift type matches staff preference")
        if candidate.fairness_impact > 0:
            reasons.append("Assignment improves schedule fairness")

        # Add constraint context
        if requirement.is_prime_shift:
            reasons.append("This is a prime/high-demand shift")

        constraint_violations = []
        if candidate.breakdown.get("clopening_penalty", 0) < 0:
            constraint_violations.append("Close-open pattern detected (soft violation)")

        reasoning = ScheduleReasoning(
            schedule_run_id=run_id,
            schedule_item_id=item_id,
            reasons=reasons,
            constraint_violations=constraint_violations,
            confidence_score=candidate.constraint_score / 100,
        )
        self.session.add(reasoning)
        await self.session.commit()
        return reasoning

    def _add_assignment_to_context(
        self,
        staff_list: List[StaffContext],
        waiter_id: UUID,
        assignment: ShiftAssignment,
    ) -> None:
        """Update staff context after assignment."""
        for staff in staff_list:
            if staff.waiter_id == waiter_id:
                staff.assigned_shifts.append(assignment)
                break

    def _calculate_hours(self, assignment: ShiftAssignment) -> float:
        """Calculate hours for an assignment."""
        start_dt = datetime.combine(assignment.shift_date, assignment.shift_start)
        end_dt = datetime.combine(assignment.shift_date, assignment.shift_end)
        if end_dt < start_dt:
            end_dt += timedelta(days=1)
        return (end_dt - start_dt).total_seconds() / 3600
