from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class WaiterTier(str, Enum):
    STRONG = "strong"
    STANDARD = "standard"
    DEVELOPING = "developing"


class StaffRole(str, Enum):
    """Staff roles - determines scheduling strategy and analytics applicability."""
    SERVER = "server"
    BARTENDER = "bartender"
    HOST = "host"
    BUSSER = "busser"
    RUNNER = "runner"


class WaiterBase(BaseModel):
    """Base schema for waiter/staff data."""

    name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    role: StaffRole = StaffRole.SERVER


class WaiterCreate(WaiterBase):
    """Schema for creating a waiter/staff member."""

    restaurant_id: UUID


class WaiterUpdate(BaseModel):
    """Schema for updating a waiter/staff member."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    role: Optional[StaffRole] = None
    is_active: Optional[bool] = None


class WaiterRead(WaiterBase):
    """Schema for reading a waiter/staff member."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    restaurant_id: UUID
    role: str = "server"  # Default for backwards compatibility
    tier: str
    composite_score: float
    tier_updated_at: Optional[datetime]
    total_shifts: int
    total_covers: int
    total_tips: float
    total_tables_served: int = 0
    total_sales: float = 0.0
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WaiterWithShiftStats(WaiterRead):
    """Waiter with current shift statistics (for routing)."""

    current_tables: int = 0
    current_tips: float = 0.0
    current_covers: int = 0
    section_id: Optional[UUID] = None
    status: str = "available"  # available, on_break, busy


class WaiterStats(BaseModel):
    """Nested stats object for waiter performance metrics."""

    covers: int
    tips: float
    avg_per_cover: float
    efficiency_pct: float
    tables_served: int
    total_sales: float


class WaiterWithStats(WaiterRead):
    """Waiter response with nested stats object."""

    stats: WaiterStats
    tenure_years: float = 0.0
