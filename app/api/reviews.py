"""
Review Management API Endpoints

Provides REST API for review ingestion, statistics, and LLM-powered analysis.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session, get_session_context
from app.models.review import Review
from app.schemas.review import ReviewCreate, ReviewRead, ReviewStats, ReviewSummary
from app.services import review_categorization, review_ingestion, review_stats, review_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])


async def _background_categorization(restaurant_id: UUID) -> None:
    """
    Background task for review categorization.
    Creates its own database session since the request session will be closed.
    """
    async with get_session_context() as session:
        try:
            result = await review_categorization.categorize_reviews_batch(
                restaurant_id, session, batch_size=25
            )
            logger.info(
                f"Background categorization completed: {result['processed']} reviews processed"
            )
        except Exception as e:
            logger.error(f"Background categorization failed: {e}")


@router.post("/{restaurant_id}/ingest")
async def ingest_reviews(
    restaurant_id: UUID,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Ingest reviews from JSON file.
    Triggers background categorization.

    Args:
        restaurant_id: UUID of the restaurant
        file: JSON file with review data
        background_tasks: FastAPI background tasks manager
        session: Database session

    Returns:
        Dictionary with ingestion results

    Example:
        curl -X POST http://localhost:8000/api/v1/reviews/{restaurant_id}/ingest \\
          -F "file=@reviews.json"
    """
    # Parse uploaded JSON
    content = await file.read()
    try:
        reviews_data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    # Validate and convert to schemas
    try:
        reviews = [ReviewCreate(**r) for r in reviews_data]
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid review data format: {str(e)}"
        )

    # Ingest reviews
    added = await review_ingestion.bulk_ingest(restaurant_id, reviews, session)

    # Note: Background categorization skipped for now to avoid async task issues
    # In production, use a proper task queue like Celery or arq
    # if background_tasks and added > 0:
    #     background_tasks.add_task(_background_categorization, restaurant_id)

    return {
        "added": added,
        "total_submitted": len(reviews),
        "status": "pending_categorization" if added > 0 else "no_new_reviews",
    }


@router.get("/{restaurant_id}/stats", response_model=ReviewStats)
async def get_stats(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ReviewStats:
    """
    Get aggregate review statistics (no LLM).

    Args:
        restaurant_id: UUID of the restaurant
        session: Database session

    Returns:
        ReviewStats with overall average, total count, and distribution

    Example:
        curl http://localhost:8000/api/v1/reviews/{restaurant_id}/stats
    """
    return await review_stats.get_review_stats(restaurant_id, session)


@router.get("/{restaurant_id}/summary", response_model=ReviewSummary)
async def get_summary(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ReviewSummary:
    """
    Get LLM-generated category opinions and summary.

    Args:
        restaurant_id: UUID of the restaurant
        session: Database session

    Returns:
        ReviewSummary with category opinions and needs_attention flag

    Example:
        curl http://localhost:8000/api/v1/reviews/{restaurant_id}/summary
    """
    return await review_summary.get_aggregate_summary(restaurant_id, session)


@router.get("/{restaurant_id}/reviews", response_model=list[ReviewRead])
async def get_reviews(
    restaurant_id: UUID,
    skip: int = 0,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[ReviewRead]:
    """
    Get paginated raw reviews.

    Args:
        restaurant_id: UUID of the restaurant
        skip: Number of reviews to skip (for pagination)
        limit: Maximum number of reviews to return

    Returns:
        List of ReviewRead objects

    Example:
        curl "http://localhost:8000/api/v1/reviews/{restaurant_id}/reviews?limit=10"
    """
    stmt = (
        select(Review)
        .where(Review.restaurant_id == restaurant_id)
        .order_by(Review.review_date.desc())
        .offset(skip)
        .limit(limit)
    )

    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("/{restaurant_id}/categorize")
async def trigger_categorization(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Manually trigger LLM categorization for pending reviews.

    Args:
        restaurant_id: UUID of the restaurant
        session: Database session

    Returns:
        Dictionary with processing results

    Example:
        curl -X POST http://localhost:8000/api/v1/reviews/{restaurant_id}/categorize
    """
    result = await review_categorization.categorize_reviews_batch(
        restaurant_id, session, batch_size=25
    )
    return result
