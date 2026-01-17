from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, Float, Boolean, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant


class Review(Base):
    """Customer review from external platforms (Yelp, Google, etc.)."""

    __tablename__ = "reviews"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Foreign key
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id", ondelete="CASCADE")
    )

    # Scraped data
    platform: Mapped[str] = mapped_column(String(50), default="yelp")
    review_identifier: Mapped[str] = mapped_column(String(255), unique=True)  # Unique per review
    rating: Mapped[int] = mapped_column(Integer)  # 1-5 stars
    text: Mapped[str] = mapped_column(Text)
    review_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # LLM-generated insights (populated after categorization)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # -1.0 to 1.0
    category_opinions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Example: {"food": "Exceptional quality...", "service": "Slow and inattentive..."}
    overall_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_attention: Mapped[bool] = mapped_column(Boolean, default=False)

    # Processing status
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # Values: "pending", "categorized", "dismissed"

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationship
    restaurant: Mapped["Restaurant"] = relationship("Restaurant", back_populates="reviews")

    def __repr__(self) -> str:
        return f"<Review(id={self.id}, platform={self.platform}, rating={self.rating})>"
