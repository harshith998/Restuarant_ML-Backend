"""Scheduling API endpoints for staff availability, preferences, and schedules."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
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
from app.schemas.scheduling import (
    # Availability
    StaffAvailabilityCreate,
    StaffAvailabilityRead,
    StaffAvailabilityUpdate,
    BulkAvailabilityCreate,
    # Preferences
    StaffPreferenceCreate,
    StaffPreferenceRead,
    StaffPreferenceUpdate,
    # Schedule
    ScheduleCreate,
    ScheduleRead,
    ScheduleUpdate,
    ScheduleWithItemsRead,
    ScheduleStatus,
    # ScheduleItem
    ScheduleItemCreate,
    ScheduleItemRead,
    ScheduleItemUpdate,
    # ScheduleRun
    ScheduleRunCreate,
    ScheduleRunRead,
    # Audit
    ScheduleAuditEntry,
    ScheduleAuditResponse,
    # Staffing Requirements
    StaffingRequirementsCreate,
    StaffingRequirementsRead,
    StaffingRequirementsUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["scheduling"])


# =============================================================================
# Staff Availability Endpoints
# =============================================================================


@router.get(
    "/staff/{waiter_id}/availability",
    response_model=List[StaffAvailabilityRead],
    summary="List staff availability patterns",
)
async def list_staff_availability(
    waiter_id: UUID,
    day_of_week: Optional[int] = Query(None, ge=0, le=6, description="Filter by day (0=Mon, 6=Sun)"),
    effective_date: Optional[date] = Query(None, description="Filter patterns effective on this date"),
    session: AsyncSession = Depends(get_session),
) -> List[StaffAvailabilityRead]:
    """Get all availability patterns for a staff member."""
    # Verify waiter exists
    waiter = await session.get(Waiter, waiter_id)
    if not waiter:
        raise HTTPException(status_code=404, detail="Staff member not found")

    stmt = select(StaffAvailability).where(StaffAvailability.waiter_id == waiter_id)

    if day_of_week is not None:
        stmt = stmt.where(StaffAvailability.day_of_week == day_of_week)

    stmt = stmt.order_by(StaffAvailability.day_of_week, StaffAvailability.start_time)
    result = await session.execute(stmt)
    availabilities = result.scalars().all()

    # Filter by effective date if provided
    if effective_date:
        availabilities = [a for a in availabilities if a.is_effective_on(effective_date)]

    return [StaffAvailabilityRead.model_validate(a) for a in availabilities]


@router.post(
    "/staff/{waiter_id}/availability",
    response_model=StaffAvailabilityRead,
    status_code=201,
    summary="Create staff availability pattern",
)
async def create_staff_availability(
    waiter_id: UUID,
    data: StaffAvailabilityCreate,
    session: AsyncSession = Depends(get_session),
) -> StaffAvailabilityRead:
    """Create a new availability pattern for a staff member."""
    waiter = await session.get(Waiter, waiter_id)
    if not waiter:
        raise HTTPException(status_code=404, detail="Staff member not found")

    availability = StaffAvailability(
        waiter_id=waiter_id,
        restaurant_id=waiter.restaurant_id,
        day_of_week=data.day_of_week,
        start_time=data.start_time,
        end_time=data.end_time,
        availability_type=data.availability_type.value,
        effective_from=data.effective_from,
        effective_until=data.effective_until,
        notes=data.notes,
    )
    session.add(availability)
    await session.commit()
    await session.refresh(availability)
    return StaffAvailabilityRead.model_validate(availability)


@router.post(
    "/staff/{waiter_id}/availability/bulk",
    response_model=List[StaffAvailabilityRead],
    status_code=201,
    summary="Create multiple availability patterns",
)
async def create_bulk_availability(
    waiter_id: UUID,
    data: BulkAvailabilityCreate,
    session: AsyncSession = Depends(get_session),
) -> List[StaffAvailabilityRead]:
    """Create multiple availability patterns at once."""
    waiter = await session.get(Waiter, waiter_id)
    if not waiter:
        raise HTTPException(status_code=404, detail="Staff member not found")

    created = []
    for entry in data.entries:
        availability = StaffAvailability(
            waiter_id=waiter_id,
            restaurant_id=waiter.restaurant_id,
            day_of_week=entry.day_of_week,
            start_time=entry.start_time,
            end_time=entry.end_time,
            availability_type=entry.availability_type.value,
            effective_from=entry.effective_from,
            effective_until=entry.effective_until,
            notes=entry.notes,
        )
        session.add(availability)
        created.append(availability)

    await session.commit()
    for a in created:
        await session.refresh(a)

    return [StaffAvailabilityRead.model_validate(a) for a in created]


@router.patch(
    "/availability/{availability_id}",
    response_model=StaffAvailabilityRead,
    summary="Update availability pattern",
)
async def update_availability(
    availability_id: UUID,
    data: StaffAvailabilityUpdate,
    session: AsyncSession = Depends(get_session),
) -> StaffAvailabilityRead:
    """Update an existing availability pattern."""
    availability = await session.get(StaffAvailability, availability_id)
    if not availability:
        raise HTTPException(status_code=404, detail="Availability pattern not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "availability_type" and value is not None:
            value = value.value
        setattr(availability, field, value)

    await session.commit()
    await session.refresh(availability)
    return StaffAvailabilityRead.model_validate(availability)


@router.delete(
    "/availability/{availability_id}",
    status_code=204,
    summary="Delete availability pattern",
)
async def delete_availability(
    availability_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete an availability pattern."""
    availability = await session.get(StaffAvailability, availability_id)
    if not availability:
        raise HTTPException(status_code=404, detail="Availability pattern not found")

    await session.delete(availability)
    await session.commit()


# =============================================================================
# Staff Preferences Endpoints
# =============================================================================


@router.get(
    "/staff/{waiter_id}/preferences",
    response_model=Optional[StaffPreferenceRead],
    summary="Get staff preferences",
)
async def get_staff_preferences(
    waiter_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> Optional[StaffPreferenceRead]:
    """Get scheduling preferences for a staff member."""
    waiter = await session.get(Waiter, waiter_id)
    if not waiter:
        raise HTTPException(status_code=404, detail="Staff member not found")

    stmt = select(StaffPreference).where(StaffPreference.waiter_id == waiter_id)
    result = await session.execute(stmt)
    preferences = result.scalar_one_or_none()

    if preferences:
        return StaffPreferenceRead.model_validate(preferences)
    return None


@router.post(
    "/staff/{waiter_id}/preferences",
    response_model=StaffPreferenceRead,
    status_code=201,
    summary="Create or update staff preferences",
)
async def upsert_staff_preferences(
    waiter_id: UUID,
    data: StaffPreferenceCreate,
    session: AsyncSession = Depends(get_session),
) -> StaffPreferenceRead:
    """Create or update scheduling preferences for a staff member."""
    waiter = await session.get(Waiter, waiter_id)
    if not waiter:
        raise HTTPException(status_code=404, detail="Staff member not found")

    # Check for existing preferences
    stmt = select(StaffPreference).where(StaffPreference.waiter_id == waiter_id)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        # Update existing
        existing.preferred_roles = [r.value for r in data.preferred_roles]
        existing.preferred_shift_types = [s.value for s in data.preferred_shift_types]
        existing.preferred_sections = [str(s) for s in data.preferred_sections]
        existing.max_shifts_per_week = data.max_shifts_per_week
        existing.max_hours_per_week = data.max_hours_per_week
        existing.min_hours_per_week = data.min_hours_per_week
        existing.avoid_clopening = data.avoid_clopening
        existing.notes = data.notes
        await session.commit()
        await session.refresh(existing)
        return StaffPreferenceRead.model_validate(existing)
    else:
        # Create new
        preferences = StaffPreference(
            waiter_id=waiter_id,
            restaurant_id=waiter.restaurant_id,
            preferred_roles=[r.value for r in data.preferred_roles],
            preferred_shift_types=[s.value for s in data.preferred_shift_types],
            preferred_sections=[str(s) for s in data.preferred_sections],
            max_shifts_per_week=data.max_shifts_per_week,
            max_hours_per_week=data.max_hours_per_week,
            min_hours_per_week=data.min_hours_per_week,
            avoid_clopening=data.avoid_clopening,
            notes=data.notes,
        )
        session.add(preferences)
        await session.commit()
        await session.refresh(preferences)
        return StaffPreferenceRead.model_validate(preferences)


# =============================================================================
# Schedule Endpoints
# =============================================================================


@router.get(
    "/restaurants/{restaurant_id}/schedules",
    response_model=List[ScheduleRead],
    summary="List schedules for restaurant",
)
async def list_schedules(
    restaurant_id: UUID,
    week_start: Optional[date] = Query(None, description="Filter by week start date"),
    status: Optional[ScheduleStatus] = Query(None, description="Filter by status"),
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> List[ScheduleRead]:
    """List schedules for a restaurant."""
    stmt = select(Schedule).where(Schedule.restaurant_id == restaurant_id)

    if week_start:
        stmt = stmt.where(Schedule.week_start_date == week_start)
    if status:
        stmt = stmt.where(Schedule.status == status.value)

    stmt = stmt.order_by(Schedule.week_start_date.desc(), Schedule.version.desc()).limit(limit)

    result = await session.execute(stmt)
    schedules = result.scalars().all()
    return [ScheduleRead.model_validate(s) for s in schedules]


@router.post(
    "/restaurants/{restaurant_id}/schedules",
    response_model=ScheduleRead,
    status_code=201,
    summary="Create a new schedule",
)
async def create_schedule(
    restaurant_id: UUID,
    data: ScheduleCreate,
    session: AsyncSession = Depends(get_session),
) -> ScheduleRead:
    """Create a new schedule for a restaurant."""
    # Check for existing schedule for this week
    stmt = select(Schedule).where(
        and_(
            Schedule.restaurant_id == restaurant_id,
            Schedule.week_start_date == data.week_start_date,
            Schedule.status != "archived",
        )
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"A schedule already exists for week starting {data.week_start_date}",
        )

    schedule = Schedule(
        restaurant_id=restaurant_id,
        week_start_date=data.week_start_date,
        status="draft",
        generated_by=data.generated_by.value,
        version=1,
    )
    session.add(schedule)
    await session.commit()
    await session.refresh(schedule)
    return ScheduleRead.model_validate(schedule)


@router.get(
    "/schedules/{schedule_id}",
    response_model=ScheduleWithItemsRead,
    summary="Get schedule with items",
)
async def get_schedule(
    schedule_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ScheduleWithItemsRead:
    """Get a schedule with all its items."""
    stmt = (
        select(Schedule)
        .where(Schedule.id == schedule_id)
        .options(selectinload(Schedule.items))
    )
    result = await session.execute(stmt)
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return ScheduleWithItemsRead.model_validate(schedule)


@router.patch(
    "/schedules/{schedule_id}",
    response_model=ScheduleRead,
    summary="Update schedule",
)
async def update_schedule(
    schedule_id: UUID,
    data: ScheduleUpdate,
    session: AsyncSession = Depends(get_session),
) -> ScheduleRead:
    """Update a schedule's status."""
    schedule = await session.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if schedule.status == "published" and data.status != ScheduleStatus.ARCHIVED:
        raise HTTPException(
            status_code=400,
            detail="Published schedules can only be archived, not modified",
        )

    if data.status:
        schedule.status = data.status.value

    await session.commit()
    await session.refresh(schedule)
    return ScheduleRead.model_validate(schedule)


@router.post(
    "/schedules/{schedule_id}/publish",
    response_model=ScheduleRead,
    summary="Publish a schedule",
)
async def publish_schedule(
    schedule_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ScheduleRead:
    """Publish a draft schedule. Creates a new version if republishing."""
    schedule = await session.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if schedule.status == "archived":
        raise HTTPException(status_code=400, detail="Cannot publish an archived schedule")

    if schedule.status == "published":
        # Create a new version
        schedule.version += 1

    schedule.status = "published"
    schedule.published_at = datetime.utcnow()

    await session.commit()
    await session.refresh(schedule)
    return ScheduleRead.model_validate(schedule)


@router.get(
    "/schedules/{schedule_id}/audit",
    response_model=ScheduleAuditResponse,
    summary="Get schedule version history",
)
async def get_schedule_audit(
    schedule_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ScheduleAuditResponse:
    """Get the version history for a schedule's week."""
    schedule = await session.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Get all versions for this week
    stmt = (
        select(Schedule)
        .where(
            and_(
                Schedule.restaurant_id == schedule.restaurant_id,
                Schedule.week_start_date == schedule.week_start_date,
            )
        )
        .options(selectinload(Schedule.items))
        .order_by(Schedule.version.desc())
    )
    result = await session.execute(stmt)
    versions = result.scalars().all()

    history = [
        ScheduleAuditEntry(
            version=v.version,
            status=ScheduleStatus(v.status),
            generated_by=v.generated_by,
            published_at=v.published_at,
            created_at=v.created_at,
            item_count=len(v.items),
        )
        for v in versions
    ]

    return ScheduleAuditResponse(
        schedule_id=schedule_id,
        restaurant_id=schedule.restaurant_id,
        week_start_date=schedule.week_start_date,
        history=history,
    )


# =============================================================================
# Schedule Item Endpoints
# =============================================================================


@router.post(
    "/schedules/{schedule_id}/items",
    response_model=ScheduleItemRead,
    status_code=201,
    summary="Add item to schedule",
)
async def create_schedule_item(
    schedule_id: UUID,
    data: ScheduleItemCreate,
    session: AsyncSession = Depends(get_session),
) -> ScheduleItemRead:
    """Add a shift assignment to a schedule."""
    schedule = await session.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if schedule.status == "published":
        raise HTTPException(status_code=400, detail="Cannot modify a published schedule")

    # Verify waiter exists and belongs to same restaurant
    waiter = await session.get(Waiter, data.waiter_id)
    if not waiter:
        raise HTTPException(status_code=404, detail="Staff member not found")
    if waiter.restaurant_id != schedule.restaurant_id:
        raise HTTPException(status_code=400, detail="Staff member does not belong to this restaurant")

    item = ScheduleItem(
        schedule_id=schedule_id,
        waiter_id=data.waiter_id,
        role=data.role.value,
        section_id=data.section_id,
        shift_date=data.shift_date,
        shift_start=data.shift_start,
        shift_end=data.shift_end,
        source=data.source.value,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return ScheduleItemRead.model_validate(item)


@router.patch(
    "/schedule-items/{item_id}",
    response_model=ScheduleItemRead,
    summary="Update schedule item",
)
async def update_schedule_item(
    item_id: UUID,
    data: ScheduleItemUpdate,
    session: AsyncSession = Depends(get_session),
) -> ScheduleItemRead:
    """Update a schedule item."""
    item = await session.get(ScheduleItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Schedule item not found")

    # Check if schedule is published
    schedule = await session.get(Schedule, item.schedule_id)
    if schedule and schedule.status == "published":
        raise HTTPException(status_code=400, detail="Cannot modify items in a published schedule")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "role" and value is not None:
            value = value.value
        setattr(item, field, value)

    await session.commit()
    await session.refresh(item)
    return ScheduleItemRead.model_validate(item)


@router.delete(
    "/schedule-items/{item_id}",
    status_code=204,
    summary="Remove schedule item",
)
async def delete_schedule_item(
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove a shift assignment from a schedule."""
    item = await session.get(ScheduleItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Schedule item not found")

    # Check if schedule is published
    schedule = await session.get(Schedule, item.schedule_id)
    if schedule and schedule.status == "published":
        raise HTTPException(status_code=400, detail="Cannot modify items in a published schedule")

    await session.delete(item)
    await session.commit()


# =============================================================================
# Schedule Run Endpoints (Scheduling Engine)
# =============================================================================


@router.post(
    "/restaurants/{restaurant_id}/schedules/run",
    response_model=ScheduleRunRead,
    status_code=202,
    summary="Trigger scheduling engine run",
)
async def create_schedule_run(
    restaurant_id: UUID,
    data: ScheduleRunCreate,
    run_engine: bool = Query(True, description="Whether to run the scheduling engine immediately"),
    session: AsyncSession = Depends(get_session),
) -> ScheduleRunRead:
    """Trigger a scheduling engine run for a week.

    The engine uses a score-and-rank algorithm to generate optimal schedules:
    1. Loads staff availability, preferences, and staffing requirements
    2. Generates demand forecast based on historical data
    3. For each required time slot, scores available staff by:
       - Constraint satisfaction (availability, max hours, etc.)
       - Preference matching (role, shift type, section)
       - Fairness impact (hours balance across staff)
    4. Assigns top-scored candidates to each slot
    5. Generates reasoning for each assignment

    Args:
        run_engine: If True (default), runs the engine immediately.
                   If False, just creates the run record for manual processing.
    """
    if run_engine:
        # Run the scheduling engine
        from app.services.scheduling_engine import SchedulingEngine

        engine = SchedulingEngine(session)
        result = await engine.run(restaurant_id, data.week_start_date)

        # Return the run status
        run = await session.get(ScheduleRun, result.schedule_run_id)
        if run:
            return ScheduleRunRead.model_validate(run)

        # Fallback if run not found (shouldn't happen)
        return ScheduleRunRead(
            id=result.schedule_run_id,
            restaurant_id=restaurant_id,
            week_start_date=data.week_start_date,
            engine_version="1.0.0",
            run_status=result.status,
            summary_metrics={
                "items_created": result.items_created,
                "total_hours": result.total_hours_scheduled,
                "coverage_pct": result.coverage_pct,
            },
            error_message=result.error_message,
            created_at=datetime.utcnow(),
        )
    else:
        # Just create a pending run record
        run = ScheduleRun(
            restaurant_id=restaurant_id,
            week_start_date=data.week_start_date,
            engine_version="1.0.0",
            run_status="pending",
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return ScheduleRunRead.model_validate(run)


@router.get(
    "/schedule-runs/{run_id}",
    response_model=ScheduleRunRead,
    summary="Get schedule run status",
)
async def get_schedule_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ScheduleRunRead:
    """Get the status and results of a scheduling engine run."""
    run = await session.get(ScheduleRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Schedule run not found")

    return ScheduleRunRead.model_validate(run)


# =============================================================================
# Staffing Requirements Endpoints
# =============================================================================


@router.get(
    "/restaurants/{restaurant_id}/staffing-requirements",
    response_model=List[StaffingRequirementsRead],
    summary="List staffing requirements",
)
async def list_staffing_requirements(
    restaurant_id: UUID,
    day_of_week: Optional[int] = Query(None, ge=0, le=6, description="Filter by day (0=Mon, 6=Sun)"),
    role: Optional[str] = Query(None, description="Filter by role"),
    effective_date: Optional[date] = Query(None, description="Filter requirements effective on this date"),
    session: AsyncSession = Depends(get_session),
) -> List[StaffingRequirementsRead]:
    """Get all staffing requirements for a restaurant."""
    stmt = select(StaffingRequirements).where(StaffingRequirements.restaurant_id == restaurant_id)

    if day_of_week is not None:
        stmt = stmt.where(StaffingRequirements.day_of_week == day_of_week)
    if role:
        stmt = stmt.where(StaffingRequirements.role == role)

    stmt = stmt.order_by(StaffingRequirements.day_of_week, StaffingRequirements.start_time)
    result = await session.execute(stmt)
    requirements = result.scalars().all()

    # Filter by effective date if provided
    if effective_date:
        requirements = [
            r for r in requirements
            if (r.effective_from is None or r.effective_from <= effective_date)
            and (r.effective_until is None or r.effective_until >= effective_date)
        ]

    return [StaffingRequirementsRead.model_validate(r) for r in requirements]


@router.post(
    "/restaurants/{restaurant_id}/staffing-requirements",
    response_model=StaffingRequirementsRead,
    status_code=201,
    summary="Create staffing requirement",
)
async def create_staffing_requirement(
    restaurant_id: UUID,
    data: StaffingRequirementsCreate,
    session: AsyncSession = Depends(get_session),
) -> StaffingRequirementsRead:
    """Create a new staffing requirement for a time slot."""
    requirement = StaffingRequirements(
        restaurant_id=restaurant_id,
        day_of_week=data.day_of_week,
        start_time=data.start_time,
        end_time=data.end_time,
        role=data.role.value,
        min_staff=data.min_staff,
        max_staff=data.max_staff,
        is_prime_shift=data.is_prime_shift,
        effective_from=data.effective_from,
        effective_until=data.effective_until,
        notes=data.notes,
    )
    session.add(requirement)
    await session.commit()
    await session.refresh(requirement)
    return StaffingRequirementsRead.model_validate(requirement)


@router.patch(
    "/staffing-requirements/{requirement_id}",
    response_model=StaffingRequirementsRead,
    summary="Update staffing requirement",
)
async def update_staffing_requirement(
    requirement_id: UUID,
    data: StaffingRequirementsUpdate,
    session: AsyncSession = Depends(get_session),
) -> StaffingRequirementsRead:
    """Update an existing staffing requirement."""
    requirement = await session.get(StaffingRequirements, requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Staffing requirement not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "role" and value is not None:
            value = value.value
        setattr(requirement, field, value)

    await session.commit()
    await session.refresh(requirement)
    return StaffingRequirementsRead.model_validate(requirement)


@router.delete(
    "/staffing-requirements/{requirement_id}",
    status_code=204,
    summary="Delete staffing requirement",
)
async def delete_staffing_requirement(
    requirement_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a staffing requirement."""
    requirement = await session.get(StaffingRequirements, requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Staffing requirement not found")

    await session.delete(requirement)
    await session.commit()
