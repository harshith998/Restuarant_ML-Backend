from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MenuItemBase(BaseModel):
    """Base schema for menu item."""

    name: str = Field(..., min_length=1, max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    price: Optional[float] = Field(None, ge=0)
    cost: Optional[float] = Field(None, ge=0)


class MenuItemCreate(MenuItemBase):
    """Schema for creating a menu item."""

    restaurant_id: UUID
    pos_item_id: Optional[str] = Field(None, max_length=100)


class MenuItemUpdate(BaseModel):
    """Schema for updating a menu item."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    price: Optional[float] = Field(None, ge=0)
    cost: Optional[float] = Field(None, ge=0)
    is_available: Optional[bool] = None


class MenuItemRead(MenuItemBase):
    """Schema for reading a menu item."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    restaurant_id: UUID
    pos_item_id: Optional[str]
    is_available: bool
    created_at: datetime
    updated_at: datetime


class OrderItemBase(BaseModel):
    """Base schema for order item."""

    quantity: int = Field(default=1, ge=1)
    unit_price: Optional[float] = Field(None, ge=0)
    total_price: Optional[float] = Field(None, ge=0)
    modifiers: Optional[Dict[str, Any]] = None


class OrderItemCreate(OrderItemBase):
    """Schema for creating an order item."""

    visit_id: UUID
    menu_item_id: UUID


class OrderItemRead(OrderItemBase):
    """Schema for reading an order item."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    visit_id: UUID
    menu_item_id: UUID
    ordered_at: datetime


# ============================================================
# Ranking and 86 Management Schemas
# ============================================================


class MenuItemRanked(BaseModel):
    """Schema for a ranked menu item with scoring metrics."""

    id: str
    name: str
    category: Optional[str]
    price: float
    cost: float
    is_available: bool

    # Ranking metrics
    combined_score: float = Field(..., description="Combined demand+margin score (0-100)")
    demand_score: float = Field(..., description="Normalized demand score (0-100)")
    margin_pct: float = Field(..., description="Profit margin percentage")
    orders_per_day: float = Field(..., description="Average orders per day")
    times_ordered: int = Field(..., description="Total times ordered in period")
    rank: int = Field(..., description="Rank position (1 = best/worst depending on sort)")


class MenuItemRankingResponse(BaseModel):
    """Response schema for ranking endpoints."""

    restaurant_id: str
    analysis_period_days: int
    total_items: int
    items: List[MenuItemRanked]


class MenuItem86Recommendation(BaseModel):
    """Schema for a single 86 recommendation."""

    id: str
    name: str
    category: Optional[str]
    price: float

    combined_score: float
    demand_score: float
    margin_pct: float
    orders_per_day: float
    reason: str = Field(..., description="Why this item is recommended for 86")


class MenuItem86RecommendationResponse(BaseModel):
    """Response schema for 86 recommendations endpoint."""

    restaurant_id: str
    analysis_period_days: int
    score_threshold: float
    total_recommendations: int
    recommendations: List[MenuItem86Recommendation]


class MenuItem86Response(BaseModel):
    """Response schema for 86/un-86 action."""

    success: bool
    item_id: str
    name: str
    is_available: bool
    message: str


class MenuItem86dListResponse(BaseModel):
    """Response schema for listing 86'd items."""

    restaurant_id: str
    total_86d: int
    items: List[Dict[str, Any]]
