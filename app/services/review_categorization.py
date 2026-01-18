"""
Review Categorization Service

Uses LLM to analyze reviews in batches and generate category opinions.
Processes pending reviews and updates them with AI-generated insights.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import Review
from app.services.llm_client import call_llm

logger = logging.getLogger(__name__)

# LLM System Prompt for Review Analysis
CATEGORIZATION_SYSTEM_PROMPT = """You are a restaurant review analyst for a southern bar and grill.

Analyze the provided reviews and generate EXTREME OPINIONS for each category. Focus on the strongest positive or negative sentiments expressed across all reviews.

Categories:
1. Food - Quality, taste, freshness, presentation
2. Service - Attentiveness, friendliness, speed, professionalism
3. Atmosphere - Ambiance, decor, noise level, comfort
4. Value - Price vs quality, portion sizes, worth
5. Cleanliness - Tables, restrooms, overall hygiene

For each category, write a 1-2 sentence NARRATIVE statement that captures the extreme (very positive OR very negative) sentiment from the reviews. Use clear, manager-friendly language.

Return JSON in this exact format:
{
  "category_opinions": {
    "food": "Brief narrative statement about food",
    "service": "Brief narrative statement about service",
    "atmosphere": "Brief narrative statement about atmosphere",
    "value": "Brief narrative statement about value",
    "cleanliness": "Brief narrative statement about cleanliness"
  },
  "overall_summary": "2-3 sentence summary of overall sentiment across all reviews",
  "needs_attention": true or false
}

Set needs_attention to true if there are significant negative themes that require management action."""


async def categorize_reviews_batch(
    restaurant_id: UUID,
    session: AsyncSession,
    batch_size: int = 25,
) -> dict:
    """
    Categorize pending reviews using LLM.
    Processes in batches of 25 reviews.
    Returns summary of processing.

    Args:
        restaurant_id: UUID of the restaurant
        session: Database session
        batch_size: Number of reviews per batch (default 25)

    Returns:
        Dictionary with processed count, batch count, and remaining count

    Example:
        >>> result = await categorize_reviews_batch(restaurant_id, session)
        >>> print(f"Processed {result['processed']} reviews in {result['batches']} batches")
    """
    # Fetch pending reviews (most recent first)
    stmt = (
        select(Review)
        .where(
            Review.restaurant_id == restaurant_id,
            Review.status == "pending",
        )
        .order_by(Review.review_date.desc())
    )

    result = await session.execute(stmt)
    pending_reviews = list(result.scalars().all())

    if not pending_reviews:
        return {"processed": 0, "batches": 0, "message": "No pending reviews"}

    total_processed = 0
    batch_count = 0

    # Process in batches
    for i in range(0, len(pending_reviews), batch_size):
        batch = pending_reviews[i : i + batch_size]
        batch_count += 1

        logger.info(f"Processing batch {batch_count} ({len(batch)} reviews)")

        # Format reviews for LLM
        review_texts = []
        for idx, review in enumerate(batch, 1):
            review_texts.append(
                f"Review {idx} [{review.rating}/5 stars]:\n{review.text}\n"
            )

        user_prompt = f"""Analyze these {len(batch)} reviews and provide your analysis:

{chr(10).join(review_texts)}

Return the JSON analysis as specified."""

        try:
            # Call LLM
            llm_response = await call_llm(
                system_prompt=CATEGORIZATION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.7,
            )

            # Update each review in batch with same insights
            # (All reviews in batch share the same aggregate analysis)
            for review in batch:
                review.category_opinions = llm_response.get("category_opinions", {})
                review.overall_summary = llm_response.get("overall_summary", "")
                review.needs_attention = llm_response.get("needs_attention", False)
                # Simple sentiment score based on needs_attention flag
                review.sentiment_score = -0.5 if review.needs_attention else 0.5
                review.status = "categorized"

            total_processed += len(batch)
            await session.commit()
            logger.info(f"Batch {batch_count} processed successfully")

        except Exception as e:
            logger.error(f"LLM categorization failed for batch {batch_count}: {e}")
            # Continue to next batch on error
            continue

    return {
        "processed": total_processed,
        "batches": batch_count,
        "pending_remaining": len(pending_reviews) - total_processed,
    }
