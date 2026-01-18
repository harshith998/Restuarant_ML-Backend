from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# Enums
# =============================================================================


class StaffRole(str, Enum):
    """Staff roles - determines scheduling strategy."""
    SERVER = "server"
    BARTENDER = "bartender"
    HOST = "host"
    BUSSER = "busser"
    RUNNER = "runner"
    CHEF = "chef"


class AvailabilityType(str, Enum):
    """Type of availability for a time slot."""
    AVAILABLE = "available"      # Can work
    UNAVAILABLE = "unavailable"  # Cannot work
    PREFERRED = "preferred"      # Wants to work (higher priority)


class ScheduleStatus(str, Enum):
    """Schedule lifecycle status."""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ScheduleSource(str, Enum):
    """How a schedule or item was created."""
    MANUAL = "manual"
    SUGGESTION = "suggestion"
    ENGINE = "engine"


class RunStatus(str, Enum):
    """Scheduling engine run status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ShiftType(str, Enum):
    """Common shift types for preferences."""
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    CLOSING = "closing"


# =============================================================================
# StaffAvailability Schemas
# =============================================================================


class StaffAvailabilityBase(BaseModel):
    """Base schema for staff availability."""
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday, 6=Sunday")
    start_time: time
    end_time: time
    availability_type: AvailabilityType = AvailabilityType.AVAILABLE
    effective_from: Optional[date] = None
    effective_until: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, v: time, info) -> time:
        """Validate end_time is after start_time (except for overnight shifts)."""
        # Allow overnight shifts where end < start
        return v


class StaffAvailabilityCreate(StaffAvailabilityBase):
    """Schema for creating staff availability."""
    pass


class StaffAvailabilityUpdate(BaseModel):
    """Schema for updating staff availability."""
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    availability_type: Optional[AvailabilityType] = None
    effective_from: Optional[date] = None
    effective_until: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=500)


class StaffAvailabilityRead(StaffAvailabilityBase):
    """Schema for reading staff availability."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    waiter_id: UUID
    restaurant_id: UUID
    created_at: datetime
    updated_at: datetime


# =============================================================================
# StaffPreference Schemas
# =============================================================================


class StaffPreferenceBase(BaseModel):
    """Base schema for staff preferences."""
    preferred_roles: List[StaffRole] = Field(default_factory=list)
    preferred_shift_types: List[ShiftType] = Field(default_factory=list)
    preferred_sections: List[UUID] = Field(default_factory=list)
    max_shifts_per_week: Optional[int] = Field(None, ge=1, le=7)
    max_hours_per_week: Optional[int] = Field(None, ge=1, le=60)
    min_hours_per_week: Optional[int] = Field(None, ge=0, le=60)
    avoid_clopening: bool = True
    notes: Optional[str] = Field(None, max_length=500)


class StaffPreferenceCreate(StaffPreferenceBase):
    """Schema for creating staff preferences."""
    pass


class StaffPreferenceUpdate(BaseModel):
    """Schema for updating staff preferences."""
    preferred_roles: Optional[List[StaffRole]] = None
    preferred_shift_types: Optional[List[ShiftType]] = None
    preferred_sections: Optional[List[UUID]] = None
    max_shifts_per_week: Optional[int] = Field(None, ge=1, le=7)
    max_hours_per_week: Optional[int] = Field(None, ge=1, le=60)
    min_hours_per_week: Optional[int] = Field(None, ge=0, le=60)
    avoid_clopening: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=500)


class StaffPreferenceRead(StaffPreferenceBase):
    """Schema for reading staff preferences."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    waiter_id: UUID
    restaurant_id: UUID
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Schedule Schemas
# =============================================================================


class ScheduleBase(BaseModel):
    """Base schema for schedules."""
    week_start_date: date
    status: ScheduleStatus = ScheduleStatus.DRAFT
    generated_by: ScheduleSource = ScheduleSource.MANUAL


class ScheduleCreate(BaseModel):
    """Schema for creating a schedule."""
    week_start_date: date
    generated_by: ScheduleSource = ScheduleSource.MANUAL


class ScheduleUpdate(BaseModel):
    """Schema for updating a schedule."""
    status: Optional[ScheduleStatus] = None


class ScheduleSummaryUpdate(BaseModel):
    """Schema for updating schedule summary."""
    schedule_summary: Optional[str] = None


class ScheduleRead(ScheduleBase):
    """Schema for reading a schedule."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    restaurant_id: UUID
    version: int
    schedule_run_id: Optional[UUID] = None
    schedule_summary: Optional[str] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ScheduleWithItemsRead(ScheduleRead):
    """Schema for reading a schedule with its items (without reasoning)."""
    items: List["ScheduleItemRead"] = Field(default_factory=list)


class ScheduleWithItemsAndReasoningRead(ScheduleRead):
    """Schema for reading a schedule with items AND AI reasoning for each item."""
    items: List["ScheduleItemWithReasoningRead"] = Field(default_factory=list)


# =============================================================================
# ScheduleItem Schemas
# =============================================================================


class ScheduleItemBase(BaseModel):
    """Base schema for schedule items."""
    waiter_id: UUID
    role: StaffRole
    section_id: Optional[UUID] = None
    shift_date: date
    shift_start: time
    shift_end: time
    source: ScheduleSource = ScheduleSource.MANUAL


class ScheduleItemCreate(ScheduleItemBase):
    """Schema for creating a schedule item."""
    pass


class ScheduleItemUpdate(BaseModel):
    """Schema for updating a schedule item."""
    waiter_id: Optional[UUID] = None
    role: Optional[StaffRole] = None
    section_id: Optional[UUID] = None
    shift_date: Optional[date] = None
    shift_start: Optional[time] = None
    shift_end: Optional[time] = None


class ScheduleItemRead(ScheduleItemBase):
    """Schema for reading a schedule item."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    schedule_id: UUID
    preference_match_score: Optional[float] = None
    fairness_impact_score: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class ScheduleItemWithReasoningRead(ScheduleItemRead):
    """Schema for reading a schedule item with reasoning."""
    reasoning: Optional["ScheduleReasoningRead"] = None


# =============================================================================
# ScheduleRun Schemas
# =============================================================================


class ScheduleRunCreate(BaseModel):
    """Schema for triggering a schedule run."""
    week_start_date: Optional[date] = None


class ScheduleRunRead(BaseModel):
    """Schema for reading a schedule run."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    restaurant_id: UUID
    week_start_date: date
    engine_version: str
    run_status: RunStatus
    inputs_snapshot: Optional[Dict[str, Any]] = None
    summary_metrics: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    # The ID of the schedule created by this run (for fetching the actual schedule)
    schedule_id: Optional[UUID] = None


class ScheduleRunDetailRead(ScheduleRunRead):
    """Schema for reading a schedule run with reasoning entries."""
    reasoning_entries: List["ScheduleReasoningRead"] = Field(default_factory=list)


# =============================================================================
# ScheduleReasoning Schemas
# =============================================================================


class ScheduleReasoningRead(BaseModel):
    """Schema for reading schedule reasoning."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    schedule_run_id: UUID
    schedule_item_id: UUID
    reasons: List[str] = Field(default_factory=list)
    constraint_violations: List[str] = Field(default_factory=list)
    confidence_score: Optional[float] = None
    created_at: datetime


# =============================================================================
# StaffingRequirements Schemas
# =============================================================================


class StaffingRequirementsBase(BaseModel):
    """Base schema for staffing requirements."""
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday, 6=Sunday")
    start_time: time
    end_time: time
    role: StaffRole
    min_staff: int = Field(1, ge=1, le=50)
    max_staff: Optional[int] = Field(None, ge=1, le=50)
    is_prime_shift: bool = False
    effective_from: Optional[date] = None
    effective_until: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=500)


class StaffingRequirementsCreate(StaffingRequirementsBase):
    """Schema for creating staffing requirements."""
    pass


class StaffingRequirementsUpdate(BaseModel):
    """Schema for updating staffing requirements."""
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    role: Optional[StaffRole] = None
    min_staff: Optional[int] = Field(None, ge=1, le=50)
    max_staff: Optional[int] = Field(None, ge=1, le=50)
    is_prime_shift: Optional[bool] = None
    effective_from: Optional[date] = None
    effective_until: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=500)


class StaffingRequirementsRead(StaffingRequirementsBase):
    """Schema for reading staffing requirements."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    restaurant_id: UUID
    role: str  # Keep as str for backwards compatibility
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Audit / History Response
# =============================================================================


class ScheduleAuditEntry(BaseModel):
    """Schema for schedule audit history entry."""
    version: int
    status: ScheduleStatus
    generated_by: ScheduleSource
    published_at: Optional[datetime] = None
    created_at: datetime
    item_count: int


class ScheduleAuditResponse(BaseModel):
    """Schema for schedule audit history response."""
    schedule_id: UUID
    restaurant_id: UUID
    week_start_date: date
    history: List[ScheduleAuditEntry]


# =============================================================================
# Bulk Operations
# =============================================================================


class BulkAvailabilityCreate(BaseModel):
    """Schema for creating multiple availability entries at once."""
    entries: List[StaffAvailabilityCreate] = Field(..., min_length=1, max_length=20)


class WeeklyAvailabilityTemplate(BaseModel):
    """Schema for setting a full week's availability at once."""
    monday: Optional[List[tuple]] = None  # [(start_time, end_time, type), ...]
    tuesday: Optional[List[tuple]] = None
    wednesday: Optional[List[tuple]] = None
    thursday: Optional[List[tuple]] = None
    friday: Optional[List[tuple]] = None
    saturday: Optional[List[tuple]] = None
    sunday: Optional[List[tuple]] = None
    effective_from: Optional[date] = None
    effective_until: Optional[date] = None


# Forward reference updates
ScheduleWithItemsRead.model_rebuild()
ScheduleWithItemsAndReasoningRead.model_rebuild()
ScheduleItemWithReasoningRead.model_rebuild()
ScheduleRunDetailRead.model_rebuild()
