from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VisitBase(BaseModel):
    """Base schema for visit data."""

    party_size: int = Field(..., ge=1, le=20)


class VisitCreate(VisitBase):
    """Schema for creating a visit (seating a table)."""

    restaurant_id: UUID
    table_id: UUID
    waiter_id: UUID
    shift_id: UUID
    waitlist_id: Optional[UUID] = None
    seated_at: datetime = Field(default_factory=datetime.utcnow)


class VisitUpdate(BaseModel):
    """Schema for updating a visit."""

    actual_covers: Optional[int] = Field(None, ge=1, le=20)
    first_served_at: Optional[datetime] = None
    payment_at: Optional[datetime] = None
    cleared_at: Optional[datetime] = None
    subtotal: Optional[float] = Field(None, ge=0)
    tax: Optional[float] = Field(None, ge=0)
    total: Optional[float] = Field(None, ge=0)
    tip: Optional[float] = Field(None, ge=0)
    pos_transaction_id: Optional[str] = None


class VisitRead(VisitBase):
    """Schema for reading a visit."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    restaurant_id: UUID
    table_id: UUID
    waiter_id: UUID
    shift_id: UUID
    waitlist_id: Optional[UUID]
    actual_covers: Optional[int]
    seated_at: datetime
    first_served_at: Optional[datetime]
    payment_at: Optional[datetime]
    cleared_at: Optional[datetime]
    duration_minutes: Optional[int]
    subtotal: Optional[float]
    tax: Optional[float]
    total: Optional[float]
    tip: Optional[float]
    tip_percentage: Optional[float]
    pos_transaction_id: Optional[str]
    original_waiter_id: Optional[UUID]
    transferred_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
