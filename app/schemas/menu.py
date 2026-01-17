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
