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


class WaiterBase(BaseModel):
    """Base schema for waiter data."""

    name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)


class WaiterCreate(WaiterBase):
    """Schema for creating a waiter."""

    restaurant_id: UUID


class WaiterUpdate(BaseModel):
    """Schema for updating a waiter."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None


class WaiterRead(WaiterBase):
    """Schema for reading a waiter."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    restaurant_id: UUID
    tier: str
    composite_score: float
    tier_updated_at: Optional[datetime]
    total_shifts: int
    total_covers: int
    total_tips: float
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
