from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.waitlist import TablePreference, LocationPreference


class RouteRequest(BaseModel):
    """Request schema for routing a party to a table."""

    waitlist_id: Optional[UUID] = None
    party_size: Optional[int] = Field(None, ge=1, le=20)
    table_preference: Optional[TablePreference] = None
    location_preference: Optional[LocationPreference] = None


class MatchDetails(BaseModel):
    """Details about how well the routing matched preferences."""

    type_matched: bool = False
    location_matched: bool = False
    capacity_fit: int = 0  # Exact capacity of assigned table


class RouteResponse(BaseModel):
    """Response schema for routing result."""

    success: bool
    table_id: Optional[UUID] = None
    table_number: Optional[str] = None
    table_type: Optional[str] = None
    table_location: Optional[str] = None
    table_capacity: Optional[int] = None
    waiter_id: Optional[UUID] = None
    waiter_name: Optional[str] = None
    section_id: Optional[UUID] = None
    section_name: Optional[str] = None
    match_details: Optional[MatchDetails] = None
    message: Optional[str] = None


class RoutingDetails(BaseModel):
    """Detailed routing information for debugging/transparency."""

    available_tables: int
    tables_matching_type: int = 0
    tables_matching_location: int = 0
    available_waiters: int
    selected_table_score: Optional[float] = None
    selected_waiter_priority: Optional[float] = None
