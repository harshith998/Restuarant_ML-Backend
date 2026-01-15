from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SectionBase(BaseModel):
    """Base schema for section data."""

    name: str = Field(..., min_length=1, max_length=100)
    is_active: bool = Field(default=True)


class SectionCreate(SectionBase):
    """Schema for creating a section."""

    restaurant_id: UUID


class SectionUpdate(BaseModel):
    """Schema for updating a section."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None


class SectionRead(SectionBase):
    """Schema for reading a section."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    restaurant_id: UUID
    created_at: datetime
