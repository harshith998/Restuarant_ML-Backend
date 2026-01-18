from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid

from sqlalchemy import JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.section import Section
    from app.models.table import Table
    from app.models.waiter import Waiter
    from app.models.shift import Shift
    from app.models.waitlist import WaitlistEntry
    from app.models.visit import Visit
    from app.models.menu import MenuItem
    from app.models.metrics import RestaurantMetrics
    from app.models.review import Review
    from app.models.ingredient import Ingredient
    from app.models.recipe import Recipe
    from app.models.kitchen_station import KitchenStation


class Restaurant(Base):
    """Multi-location restaurant entity."""

    __tablename__ = "restaurants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="America/New_York")
    yelp_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=lambda: {})
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    sections: Mapped[List["Section"]] = relationship(
        "Section", back_populates="restaurant", cascade="all, delete-orphan"
    )
    tables: Mapped[List["Table"]] = relationship(
        "Table", back_populates="restaurant", cascade="all, delete-orphan"
    )
    waiters: Mapped[List["Waiter"]] = relationship(
        "Waiter", back_populates="restaurant", cascade="all, delete-orphan"
    )
    shifts: Mapped[List["Shift"]] = relationship(
        "Shift", back_populates="restaurant", cascade="all, delete-orphan"
    )
    waitlist_entries: Mapped[List["WaitlistEntry"]] = relationship(
        "WaitlistEntry", back_populates="restaurant", cascade="all, delete-orphan"
    )
    visits: Mapped[List["Visit"]] = relationship(
        "Visit", back_populates="restaurant", cascade="all, delete-orphan"
    )
    menu_items: Mapped[List["MenuItem"]] = relationship(
        "MenuItem", back_populates="restaurant", cascade="all, delete-orphan"
    )
    metrics: Mapped[List["RestaurantMetrics"]] = relationship(
        "RestaurantMetrics", back_populates="restaurant", cascade="all, delete-orphan"
    )
    reviews: Mapped[List["Review"]] = relationship(
        "Review", back_populates="restaurant", cascade="all, delete-orphan"
    )
    ingredients: Mapped[List["Ingredient"]] = relationship(
        "Ingredient", back_populates="restaurant", cascade="all, delete-orphan"
    )
    kitchen_stations: Mapped[List["KitchenStation"]] = relationship(
        "KitchenStation", back_populates="restaurant", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Restaurant(id={self.id}, name={self.name})>"
