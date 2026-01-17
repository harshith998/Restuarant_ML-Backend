from __future__ import annotations

from typing import TYPE_CHECKING
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant


class KitchenStation(Base):
    """Kitchen prep stations."""

    __tablename__ = "kitchen_stations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_concurrent_orders: Mapped[int] = mapped_column(Integer, default=10)

    restaurant: Mapped["Restaurant"] = relationship("Restaurant", back_populates="kitchen_stations")

    def __repr__(self) -> str:
        return f"<KitchenStation(id={self.id}, name={self.name})>"
