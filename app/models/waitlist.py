from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant
    from app.models.visit import Visit


class WaitlistEntry(Base):
    """Waitlist queue entries."""

    __tablename__ = "waitlist"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )

    party_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False)
    table_preference: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # booth, bar, table, none
    location_preference: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # inside, outside, patio, none
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    checked_in_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    quoted_wait_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Resolution
    status: Mapped[str] = mapped_column(String(20), default="waiting")  # waiting, seated, walked_away
    seated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    walked_away_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Link to visit when seated
    visit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    restaurant: Mapped["Restaurant"] = relationship(
        "Restaurant", back_populates="waitlist_entries"
    )
    visit: Mapped[Optional["Visit"]] = relationship(
        "Visit", back_populates="waitlist_entry"
    )

    def __repr__(self) -> str:
        return f"<WaitlistEntry(id={self.id}, party_name={self.party_name}, size={self.party_size})>"
