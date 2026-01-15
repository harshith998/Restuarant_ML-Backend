from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List
import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant
    from app.models.table import Table
    from app.models.shift import Shift


class Section(Base):
    """Sections within a restaurant."""

    __tablename__ = "sections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    restaurant: Mapped["Restaurant"] = relationship(
        "Restaurant", back_populates="sections"
    )
    tables: Mapped[List["Table"]] = relationship(
        "Table", back_populates="section", cascade="all, delete-orphan"
    )
    shifts: Mapped[List["Shift"]] = relationship(
        "Shift", back_populates="section"
    )

    def __repr__(self) -> str:
        return f"<Section(id={self.id}, name={self.name})>"
