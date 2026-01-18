"""
Review Summary Service

Retrieves aggregate summary from categorized reviews.
Returns the most recent LLM-generated category opinions.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import Review
from app.schemas.review import CategoryOpinions, ReviewSummary


async def get_aggregate_summary(
    restaurant_id: UUID,
    session: AsyncSession,
) -> ReviewSummary:
    """
    Get aggregate summary from categorized reviews.
    Uses most recent categorization results.

    Args:
        restaurant_id: UUID of the restaurant
        session: Database session

    Returns:
        ReviewSummary with category opinions and overall summary

    Example:
        >>> summary = await get_aggregate_summary(restaurant_id, session)
        >>> print(summary.category_opinions.food)
        >>> print(summary.overall_summary)
    """
    # Get most recently categorized review (all in batch share same analysis)
    stmt = (
        select(Review)
        .where(
            Review.restaurant_id == restaurant_id,
            Review.status == "categorized",
            Review.category_opinions.isnot(None),
        )
        .order_by(Review.updated_at.desc())
        .limit(1)
    )

    result = await session.execute(stmt)
    latest = result.scalar_one_or_none()

    if not latest:
        # No categorized reviews yet - return default
        return ReviewSummary(
            category_opinions=CategoryOpinions(
                food="Not enough data",
                service="Not enough data",
                atmosphere="Not enough data",
                value="Not enough data",
                cleanliness="Not enough data",
            ),
            overall_summary="No reviews have been analyzed yet.",
            needs_attention=False,
        )

    # Return latest categorization
    return ReviewSummary(
        category_opinions=CategoryOpinions(**latest.category_opinions),
        overall_summary=latest.overall_summary or "",
        needs_attention=latest.needs_attention,
    )
