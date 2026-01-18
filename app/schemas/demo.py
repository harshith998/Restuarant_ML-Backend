from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DemoSource(BaseModel):
    """Single demo source for replay."""

    camera_id: str = Field(..., min_length=1)
    results_path: str = Field(..., min_length=1)
    table_map: Optional[Dict[str, str]] = None  # JSON table_number -> DB table_number


class DemoInitiateRequest(BaseModel):
    """Request payload to start demo replay."""

    restaurant_id: str
    demos: List[DemoSource]
    speed: float = Field(1.0, gt=0)
    overwrite: bool = True
    mapping_mode: str = Field("auto", pattern="^(auto|direct_only)$")
    seed_shift_snapshot: Optional["DemoShiftSeedRequest"] = None


class DemoShiftSeedWaiter(BaseModel):
    """Waiter seed data for demo shift snapshot."""

    name: str = Field(..., min_length=1)
    section_name: Optional[str] = None
    tier: Optional[str] = None
    composite_score: Optional[float] = Field(None, ge=0)
    tables_served: int = Field(0, ge=0)
    current_tables: int = Field(0, ge=0)
    total_tips: float = Field(0, ge=0)
    total_covers: int = Field(0, ge=0)


class DemoShiftSeedRequest(BaseModel):
    """Optional seed request to create active shifts for demo."""

    enabled: bool = False
    waiters: List[DemoShiftSeedWaiter] = Field(default_factory=list)


class DemoSeededWaiter(BaseModel):
    """Seeded waiter metadata returned in demo initiate."""

    waiter_id: UUID
    shift_id: UUID
    name: str
    current_tables: int


class DemoInitiateResponse(BaseModel):
    """Response when demo replay starts."""

    status: str
    session_id: UUID
    camera_count: int
    mapping_mode: str
    warnings: List[str] = Field(default_factory=list)
    seeded_waiters: List[DemoSeededWaiter] = Field(default_factory=list)


class DemoCameraStatus(BaseModel):
    """Per-camera status for an active demo."""

    camera_id: str
    results_path: str
    total_frames: int
    current_frame_index: int = -1
    last_timestamp_s: Optional[float] = None


class DemoStatusResponse(BaseModel):
    """Status for the current demo session."""

    status: str
    session_id: Optional[UUID] = None
    running: bool = False
    started_at: Optional[datetime] = None
    speed: Optional[float] = None
    cameras: List[DemoCameraStatus] = Field(default_factory=list)


class DemoStopResponse(BaseModel):
    """Response when demo replay stops."""

    status: str


class DemoSummaryTable(BaseModel):
    """Available table summary for host UI."""

    table_id: UUID
    table_number: str
    capacity: int
    table_type: str
    location: str
    section_id: Optional[UUID]
    section_name: Optional[str]


class DemoSummaryWaiter(BaseModel):
    """Ranked waiter summary for host UI."""

    waiter_id: UUID
    name: str
    tier: str
    section_id: Optional[UUID]
    status: str
    current_tables: int
    current_covers: int
    current_tips: float
    priority_score: Optional[float] = None
    rank: int


class DemoSummaryResponse(BaseModel):
    """Summary data for demo host UI top cards."""

    generated_at: datetime
    routing_mode: str
    open_tables_count: int
    tables: List[DemoSummaryTable]
    waiters: List[DemoSummaryWaiter]
