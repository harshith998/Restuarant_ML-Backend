from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant
    from app.models.visit import Visit
    from app.models.metrics import MenuItemMetrics
    from app.models.recipe import Recipe


class MenuItem(Base):
    """Menu items (populated from POS)."""

    __tablename__ = "menu_items"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "pos_item_id", name="uq_restaurant_pos_item"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )
    pos_item_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    cost: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)  # If available

    is_available: Mapped[bool] = mapped_column(Boolean, default=True)  # 86'd = False

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    restaurant: Mapped["Restaurant"] = relationship(
        "Restaurant", back_populates="menu_items"
    )
    order_items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem", back_populates="menu_item"
    )
    metrics: Mapped[List["MenuItemMetrics"]] = relationship(
        "MenuItemMetrics", back_populates="menu_item", cascade="all, delete-orphan"
    )
    recipes: Mapped[List["Recipe"]] = relationship(
        "Recipe", back_populates="menu_item", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<MenuItem(id={self.id}, name={self.name}, price={self.price})>"


class OrderItem(Base):
    """Order line items (from POS webhooks)."""

    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id"), nullable=False
    )
    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menu_items.id"), nullable=False
    )

    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    total_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    modifiers: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    ordered_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    visit: Mapped["Visit"] = relationship(
        "Visit", back_populates="order_items"
    )
    menu_item: Mapped["MenuItem"] = relationship(
        "MenuItem", back_populates="order_items"
    )
    

    def __repr__(self) -> str:
        return f"<OrderItem(id={self.id}, menu_item_id={self.menu_item_id}, quantity={self.quantity})>"
