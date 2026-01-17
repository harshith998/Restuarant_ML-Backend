"""Waiter insights model for storing LLM-generated analysis and tier data."""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid

from sqlalchemy import Date, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.waiter import Waiter
    from app.models.restaurant import Restaurant


def _empty_list() -> List[Any]:
    """Factory for empty list default."""
    return []


def _empty_dict() -> Dict[str, Any]:
    """Factory for empty dict default."""
    return {}


class WaiterInsights(Base):
    """
    Stores LLM-generated insights and tier calculations for waiters.

    Cached weekly by the tier recalculation job.
    """

    __tablename__ = "waiter_insights"
    __table_args__ = (
        UniqueConstraint(
            "waiter_id", "period_start",
            name="uq_waiter_insights_period"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    waiter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waiters.id"), nullable=False
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )

    # Computed scores
    math_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="PRD formula result (0-100)"
    )
    llm_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="LLM final score (0-100)"
    )
    composite_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="Final score used for tier"
    )
    tier: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="strong/standard/developing"
    )

    # Z-score components (for transparency/debugging)
    turn_time_zscore: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    tip_pct_zscore: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    covers_zscore: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    # LLM-generated content (stored as JSON)
    strengths: Mapped[Optional[List[Any]]] = mapped_column(
        JSON, default=_empty_list, comment='["Fast table turns (47min avg)", ...]'
    )
    areas_to_watch: Mapped[Optional[List[Any]]] = mapped_column(
        JSON, default=_empty_list, comment='["Lower wine upsells than average", ...]'
    )
    suggestions: Mapped[Optional[List[Any]]] = mapped_column(
        JSON, default=_empty_list, comment='["Consider wine pairing training", ...]'
    )
    llm_summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Full LLM analysis text"
    )

    # Trend data for 6-month chart
    monthly_trends: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, default=_empty_dict,
        comment='{"2024-09": {"tips": 3800, "covers": 120}, ...}'
    )

    # Raw metrics snapshot (for reference)
    metrics_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, default=_empty_dict,
        comment="Raw metrics used for calculation"
    )

    # Metadata
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    llm_model: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Model used for scoring"
    )

    # Relationships
    waiter: Mapped["Waiter"] = relationship(
        "Waiter", back_populates="insights"
    )
    restaurant: Mapped["Restaurant"] = relationship("Restaurant")

    def __repr__(self) -> str:
        return (
            f"<WaiterInsights(waiter_id={self.waiter_id}, "
            f"tier={self.tier}, score={self.composite_score})>"
        )

    @property
    def is_current(self) -> bool:
        """Check if this insight is from the current period."""
        if self.period_end is None:
            return True
        return date.today() <= self.period_end
