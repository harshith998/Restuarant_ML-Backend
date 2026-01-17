from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List
import uuid

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant
    from app.models.recipe import Recipe


class Ingredient(Base):
    """Raw ingredients for menu items."""

    __tablename__ = "ingredients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    cost_per_unit: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    supplier: Mapped[str] = mapped_column(String(255), nullable=False)
    par_level: Mapped[int] = mapped_column(nullable=False)
    current_stock: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    restaurant: Mapped["Restaurant"] = relationship("Restaurant", back_populates="ingredients")
    recipes: Mapped[List["Recipe"]] = relationship("Recipe", back_populates="ingredient", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Ingredient(id={self.id}, name={self.name})>"
