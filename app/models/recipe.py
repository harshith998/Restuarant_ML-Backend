from __future__ import annotations

from typing import TYPE_CHECKING
import uuid

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.menu import MenuItem
    from app.models.ingredient import Ingredient


class Recipe(Base):
    """Ingredients needed for each menu item."""

    __tablename__ = "recipes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menu_items.id"), nullable=False
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id"), nullable=False
    )

    quantity: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str] = mapped_column(String(500), nullable=True)

    menu_item: Mapped["MenuItem"] = relationship("MenuItem", back_populates="recipes")
    ingredient: Mapped["Ingredient"] = relationship("Ingredient", back_populates="recipes")

    def __repr__(self) -> str:
        return f"<Recipe(menu_item_id={self.menu_item_id}, quantity={self.quantity})>"
