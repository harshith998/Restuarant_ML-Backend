from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RestaurantBase(BaseModel):
    """Base schema for restaurant data."""

    name: str = Field(..., min_length=1, max_length=255)
    timezone: str = Field(default="America/New_York", max_length=50)
    config: Dict[str, Any] = Field(default_factory=dict)


class RestaurantCreate(RestaurantBase):
    """Schema for creating a restaurant."""

    pass


class RestaurantUpdate(BaseModel):
    """Schema for updating a restaurant."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    timezone: Optional[str] = Field(None, max_length=50)
    config: Optional[Dict[str, Any]] = None


class RestaurantRead(RestaurantBase):
    """Schema for reading a restaurant."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
