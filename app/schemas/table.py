from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TableType(str, Enum):
    BOOTH = "booth"
    TABLE = "table"


class TableLocation(str, Enum):
    INSIDE = "inside"
    OUTSIDE = "outside"


class TableState(str, Enum):
    CLEAN = "clean"
    OCCUPIED = "occupied"
    DIRTY = "dirty"
    RESERVED = "reserved"
    UNAVAILABLE = "unavailable"


class TableBase(BaseModel):
    """Base schema for table data."""

    table_number: str = Field(..., min_length=1, max_length=20)
    capacity: int = Field(..., ge=1, le=20)
    table_type: TableType
    location: TableLocation = TableLocation.INSIDE


class TableCreate(TableBase):
    """Schema for creating a table."""

    restaurant_id: UUID
    section_id: Optional[UUID] = None


class TableUpdate(BaseModel):
    """Schema for updating a table."""

    table_number: Optional[str] = Field(None, min_length=1, max_length=20)
    capacity: Optional[int] = Field(None, ge=1, le=20)
    table_type: Optional[TableType] = None
    location: Optional[TableLocation] = None
    section_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class TableStateUpdate(BaseModel):
    """Schema for updating table state (from ML or host)."""

    state: TableState
    source: str = Field(..., pattern="^(ml|host|system)$")
    confidence: Optional[float] = Field(None, ge=0, le=1)


class TableRead(BaseModel):
    """Schema for reading a table."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    restaurant_id: UUID
    section_id: Optional[UUID]
    table_number: str
    capacity: int
    table_type: str
    location: str
    state: str
    state_confidence: Optional[float]
    state_updated_at: Optional[datetime]
    current_visit_id: Optional[UUID]
    is_active: bool
    created_at: datetime
    updated_at: datetime
