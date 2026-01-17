"""
Review Statistics Service

Calculates aggregate review statistics using pure SQL queries.
No LLM calls - only mathematical aggregations.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import Review
from app.schemas.review import RatingDistribution, ReviewStats


async def get_review_stats(
    restaurant_id: UUID,
    session: AsyncSession,
) -> ReviewStats:
    """
    Calculate review statistics from raw data.
    No LLM calls - pure SQL aggregation.

    Args:
        restaurant_id: UUID of the restaurant
        session: Database session

    Returns:
        ReviewStats with overall average, total count, distribution

    Example:
        >>> stats = await get_review_stats(restaurant_id, session)
        >>> print(f"Average: {stats.overall_average}, Total: {stats.total_reviews}")
    """
    # Overall average and count
    stmt = select(
        func.count(Review.id),
        func.avg(Review.rating),
    ).where(Review.restaurant_id == restaurant_id)

    result = await session.execute(stmt)
    total_count, avg_rating = result.one()

    # This month's count
    month_start = datetime.utcnow().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    stmt = select(func.count(Review.id)).where(
        Review.restaurant_id == restaurant_id,
        Review.review_date >= month_start,
    )
    result = await session.execute(stmt)
    this_month = result.scalar()

    # Rating distribution (count for each star level)
    distribution = {}
    for stars in range(1, 6):
        stmt = select(func.count(Review.id)).where(
            Review.restaurant_id == restaurant_id,
            Review.rating == stars,
        )
        result = await session.execute(stmt)
        distribution[stars] = result.scalar() or 0

    return ReviewStats(
        overall_average=round(avg_rating or 0.0, 2),
        total_reviews=total_count or 0,
        reviews_this_month=this_month or 0,
        rating_distribution=RatingDistribution(
            five_star=distribution[5],
            four_star=distribution[4],
            three_star=distribution[3],
            two_star=distribution[2],
            one_star=distribution[1],
        ),
    )
