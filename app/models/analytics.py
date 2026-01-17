"""Schedule insights model for caching analytics and LLM-generated observations."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid

from sqlalchemy import Date, DateTime, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.scheduling import Schedule
    from app.models.restaurant import Restaurant


def _empty_list() -> List[Any]:
    """Factory for empty list default."""
    return []


def _empty_dict() -> Dict[str, Any]:
    """Factory for empty dict default."""
    return {}


class ScheduleInsights(Base):
    """
    Caches analytics and LLM-generated insights for schedules.

    Insights are regenerated when:
    - Schedule changes (version bump)
    - Cache expires (default 24 hours)
    - Force refresh requested
    """

    __tablename__ = "schedule_insights"
    __table_args__ = (
        UniqueConstraint(
            "schedule_id",
            name="uq_schedule_insights_schedule"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedules.id"), nullable=False, unique=True
    )
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False
    )

    # Cached metrics summary
    coverage_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="% of required slots filled"
    )
    gini_coefficient: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4), nullable=True, comment="Hours distribution fairness (0-1)"
    )
    avg_preference_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="Avg preference match (0-100)"
    )

    # Insight counts by severity
    critical_count: Mapped[int] = mapped_column(default=0)
    warning_count: Mapped[int] = mapped_column(default=0)
    info_count: Mapped[int] = mapped_column(default=0)

    # Categorized insights (stored as JSON)
    coverage_insights: Mapped[Optional[List[Any]]] = mapped_column(
        JSON, default=_empty_list, comment="Coverage gap insights"
    )
    fairness_insights: Mapped[Optional[List[Any]]] = mapped_column(
        JSON, default=_empty_list, comment="Fairness issue insights"
    )
    pattern_insights: Mapped[Optional[List[Any]]] = mapped_column(
        JSON, default=_empty_list, comment="Pattern detection insights (clopening, etc.)"
    )

    # LLM-generated content
    llm_summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="LLM-generated summary paragraph"
    )
    llm_model: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="Model used for summary generation"
    )

    # Detailed metrics snapshot (for debugging/reference)
    metrics_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, default=_empty_dict,
        comment="Full metrics used for insight generation"
    )

    # Cache metadata
    schedule_version: Mapped[int] = mapped_column(
        default=1, comment="Schedule version when insights were generated"
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow() + timedelta(hours=24)
    )

    # Standard timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    schedule: Mapped["Schedule"] = relationship(
        "Schedule", back_populates="insights"
    )
    restaurant: Mapped["Restaurant"] = relationship("Restaurant")

    def __repr__(self) -> str:
        return (
            f"<ScheduleInsights(schedule_id={self.schedule_id}, "
            f"coverage={self.coverage_pct}%, gini={self.gini_coefficient})>"
        )

    @property
    def is_expired(self) -> bool:
        """Check if the cached insights have expired."""
        return datetime.utcnow() > self.expires_at

    @property
    def total_insights(self) -> int:
        """Total count of all insights."""
        return self.critical_count + self.warning_count + self.info_count

    def needs_refresh(self, current_schedule_version: int) -> bool:
        """Check if insights need to be regenerated."""
        if self.is_expired:
            return True
        if self.schedule_version != current_schedule_version:
            return True
        return False
