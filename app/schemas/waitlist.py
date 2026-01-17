from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TablePreference(str, Enum):
    BOOTH = "booth"
    BAR = "bar"
    TABLE = "table"
    NONE = "none"


class LocationPreference(str, Enum):
    INSIDE = "inside"
    OUTSIDE = "outside"
    PATIO = "patio"
    NONE = "none"


class WaitlistStatus(str, Enum):
    WAITING = "waiting"
    SEATED = "seated"
    WALKED_AWAY = "walked_away"


class WaitlistBase(BaseModel):
    """Base schema for waitlist entry."""

    party_name: Optional[str] = Field(None, max_length=100)
    party_size: int = Field(..., ge=1, le=20)
    table_preference: Optional[TablePreference] = None
    location_preference: Optional[LocationPreference] = None
    notes: Optional[str] = None


class WaitlistCreate(WaitlistBase):
    """Schema for creating a waitlist entry."""

    restaurant_id: UUID
    quoted_wait_minutes: Optional[int] = Field(None, ge=0)


class WaitlistUpdate(BaseModel):
    """Schema for updating a waitlist entry."""

    party_name: Optional[str] = Field(None, max_length=100)
    party_size: Optional[int] = Field(None, ge=1, le=20)
    table_preference: Optional[TablePreference] = None
    location_preference: Optional[LocationPreference] = None
    notes: Optional[str] = None
    quoted_wait_minutes: Optional[int] = Field(None, ge=0)
    status: Optional[WaitlistStatus] = None


class WaitlistRead(BaseModel):
    """Schema for reading a waitlist entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    restaurant_id: UUID
    party_name: Optional[str]
    party_size: int
    table_preference: Optional[str]
    location_preference: Optional[str]
    notes: Optional[str]
    checked_in_at: datetime
    quoted_wait_minutes: Optional[int]
    status: str
    seated_at: Optional[datetime]
    walked_away_at: Optional[datetime]
    visit_id: Optional[UUID]
    created_at: datetime
