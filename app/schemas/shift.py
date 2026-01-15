from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ShiftStatus(str, Enum):
    ACTIVE = "active"
    ON_BREAK = "on_break"
    ENDED = "ended"


class ShiftBase(BaseModel):
    """Base schema for shift data."""

    clock_in: datetime


class ShiftCreate(ShiftBase):
    """Schema for creating a shift (clock in)."""

    restaurant_id: UUID
    waiter_id: UUID
    section_id: Optional[UUID] = None


class ShiftUpdate(BaseModel):
    """Schema for updating a shift."""

    clock_out: Optional[datetime] = None
    status: Optional[ShiftStatus] = None
    section_id: Optional[UUID] = None


class ShiftRead(ShiftBase):
    """Schema for reading a shift."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    restaurant_id: UUID
    waiter_id: UUID
    section_id: Optional[UUID]
    clock_out: Optional[datetime]
    status: str
    tables_served: int
    total_covers: int
    total_tips: float
    total_sales: float
    created_at: datetime
    updated_at: datetime
