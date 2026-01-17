"""
Review Ingestion Service

Handles bulk ingestion of scraped reviews from JSON files.
Skips duplicates by review_identifier and manages batch imports.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import Review
from app.schemas.review import ReviewCreate

logger = logging.getLogger(__name__)


async def bulk_ingest(
    restaurant_id: UUID,
    reviews: list[ReviewCreate],
    session: AsyncSession,
) -> int:
    """
    Ingest reviews from scraper JSON.
    Skips duplicates by review_identifier.
    Returns count of newly added reviews.

    Args:
        restaurant_id: UUID of the restaurant
        reviews: List of review data from scraper
        session: Database session

    Returns:
        Number of newly added reviews (duplicates skipped)

    Example:
        >>> reviews_data = [ReviewCreate(...), ...]
        >>> added = await bulk_ingest(restaurant_id, reviews_data, session)
        >>> print(f"Added {added} new reviews")
    """
    added = 0

    for review_data in reviews:
        # Check for duplicate by review_identifier
        stmt = select(Review).where(
            Review.review_identifier == review_data.review_identifier
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(f"Skipping duplicate: {review_data.review_identifier}")
            continue

        # Create new review with pending status
        review = Review(
            restaurant_id=restaurant_id,
            platform=review_data.platform,
            review_identifier=review_data.review_identifier,
            rating=review_data.rating,
            text=review_data.text,
            review_date=review_data.review_date,
            status="pending",
        )
        session.add(review)
        added += 1

    await session.commit()
    logger.info(f"Ingested {added} new reviews (skipped {len(reviews) - added} duplicates)")
    return added
