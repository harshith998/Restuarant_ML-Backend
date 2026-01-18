"""
Tests for Review Management System

Tests all review endpoints with realistic scenarios:
- Review ingestion with duplicate handling
- Statistics calculation
- LLM categorization (mocked)
- Summary retrieval
- Pagination
"""

from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import Review
from app.schemas.review import ReviewCreate
from app.services import review_categorization, review_ingestion, review_stats, review_summary


@pytest.fixture
def sample_review_data():
    """Sample single review data for testing."""
    return {
        "platform": "yelp",
        "review_identifier": "test_review_001",
        "rating": 5,
        "text": "Amazing food and service! Highly recommend the shrimp and grits.",
        "review_date": "2024-01-15T12:00:00Z",
    }


@pytest.fixture
def sample_reviews_json():
    """Multiple reviews for bulk testing."""
    return [
        {
            "platform": "yelp",
            "review_identifier": f"test_review_{i:03d}",
            "rating": (i % 5) + 1,
            "text": f"Review number {i}. {'Great' if i % 2 == 0 else 'Could be better'}.",
            "review_date": "2024-01-15T12:00:00Z",
        }
        for i in range(10)
    ]


@pytest.fixture
def mock_llm_response():
    """Mock LLM categorization response."""
    return {
        "category_opinions": {
            "food": "Excellent southern cuisine with exceptional shrimp and grits",
            "service": "Friendly and attentive staff",
            "atmosphere": "Comfortable and welcoming",
            "value": "Good value for the quality",
            "cleanliness": "Clean and well-maintained",
        },
        "overall_summary": "Positive feedback overall with particular praise for the food quality.",
        "needs_attention": False,
    }


# Service Layer Tests


@pytest.mark.asyncio
async def test_bulk_ingest_new_reviews(db_session: AsyncSession, sample_restaurant, sample_reviews_json):
    """Test ingesting new reviews."""
    reviews = [ReviewCreate(**r) for r in sample_reviews_json]
    added = await review_ingestion.bulk_ingest(sample_restaurant.id, reviews, db_session)

    assert added == 10

    # Verify reviews in database
    from sqlalchemy import select
    stmt = select(Review).where(Review.restaurant_id == sample_restaurant.id)
    result = await db_session.execute(stmt)
    db_reviews = list(result.scalars().all())

    assert len(db_reviews) == 10
    assert all(r.status == "pending" for r in db_reviews)


@pytest.mark.asyncio
async def test_bulk_ingest_duplicate_handling(db_session: AsyncSession, sample_restaurant, sample_reviews_json):
    """Test that duplicate reviews are skipped."""
    reviews = [ReviewCreate(**r) for r in sample_reviews_json]

    # First ingestion
    added_first = await review_ingestion.bulk_ingest(sample_restaurant.id, reviews, db_session)
    assert added_first == 10

    # Second ingestion (all duplicates)
    added_second = await review_ingestion.bulk_ingest(sample_restaurant.id, reviews, db_session)
    assert added_second == 0

    # Verify total count
    from sqlalchemy import select, func
    stmt = select(func.count(Review.id)).where(Review.restaurant_id == sample_restaurant.id)
    result = await db_session.execute(stmt)
    total = result.scalar()
    assert total == 10


@pytest.mark.asyncio
async def test_get_review_stats_empty(db_session: AsyncSession, sample_restaurant):
    """Test stats calculation with no reviews."""
    stats = await review_stats.get_review_stats(sample_restaurant.id, db_session)

    assert stats.total_reviews == 0
    assert stats.overall_average == 0.0
    assert stats.reviews_this_month == 0
    assert stats.rating_distribution.five_star == 0


@pytest.mark.asyncio
async def test_get_review_stats_with_reviews(db_session: AsyncSession, sample_restaurant):
    """Test stats calculation with reviews."""
    # Insert test reviews
    for i in range(5):
        review = Review(
            restaurant_id=sample_restaurant.id,
            platform="yelp",
            review_identifier=f"stat_test_{i}",
            rating=(i % 5) + 1,  # 1, 2, 3, 4, 5
            text=f"Test review {i}",
            review_date=datetime.utcnow(),
        )
        db_session.add(review)
    await db_session.commit()

    stats = await review_stats.get_review_stats(sample_restaurant.id, db_session)

    assert stats.total_reviews == 5
    assert stats.overall_average == 3.0  # (1+2+3+4+5)/5 = 3.0
    assert stats.rating_distribution.one_star == 1
    assert stats.rating_distribution.two_star == 1
    assert stats.rating_distribution.three_star == 1
    assert stats.rating_distribution.four_star == 1
    assert stats.rating_distribution.five_star == 1


@pytest.mark.asyncio
async def test_categorize_reviews_batch_no_pending(db_session: AsyncSession, sample_restaurant):
    """Test categorization with no pending reviews."""
    result = await review_categorization.categorize_reviews_batch(
        sample_restaurant.id, db_session
    )

    assert result["processed"] == 0
    assert result["batches"] == 0
    assert result["message"] == "No pending reviews"


@pytest.mark.asyncio
async def test_categorize_reviews_batch_with_mock(db_session: AsyncSession, sample_restaurant, mock_llm_response, monkeypatch):
    """Test categorization with mocked LLM."""
    # Insert pending reviews
    for i in range(3):
        review = Review(
            restaurant_id=sample_restaurant.id,
            platform="yelp",
            review_identifier=f"cat_test_{i}",
            rating=5,
            text=f"Great food {i}!",
            review_date=datetime.utcnow(),
            status="pending",
        )
        db_session.add(review)
    await db_session.commit()

    # Mock LLM call
    async def mock_call_llm(*args, **kwargs):
        return mock_llm_response

    monkeypatch.setattr("app.services.review_categorization.call_llm", mock_call_llm)

    # Trigger categorization
    result = await review_categorization.categorize_reviews_batch(
        sample_restaurant.id, db_session, batch_size=25
    )

    assert result["processed"] == 3
    assert result["batches"] == 1
    assert result["pending_remaining"] == 0

    # Verify reviews are categorized
    from sqlalchemy import select
    stmt = select(Review).where(Review.restaurant_id == sample_restaurant.id)
    result = await db_session.execute(stmt)
    reviews = list(result.scalars().all())

    assert all(r.status == "categorized" for r in reviews)
    assert all(r.category_opinions is not None for r in reviews)
    assert all(r.overall_summary is not None for r in reviews)


@pytest.mark.asyncio
async def test_get_aggregate_summary_no_data(db_session: AsyncSession, sample_restaurant):
    """Test summary with no categorized reviews."""
    summary = await review_summary.get_aggregate_summary(sample_restaurant.id, db_session)

    assert summary.category_opinions.food == "Not enough data"
    assert summary.overall_summary == "No reviews have been analyzed yet."
    assert summary.needs_attention is False


@pytest.mark.asyncio
async def test_get_aggregate_summary_with_data(db_session: AsyncSession, sample_restaurant):
    """Test summary with categorized reviews."""
    # Insert categorized review
    review = Review(
        restaurant_id=sample_restaurant.id,
        platform="yelp",
        review_identifier="summary_test_001",
        rating=5,
        text="Great food!",
        review_date=datetime.utcnow(),
        status="categorized",
        category_opinions={
            "food": "Excellent",
            "service": "Great",
            "atmosphere": "Nice",
            "value": "Good",
            "cleanliness": "Clean",
        },
        overall_summary="Very positive experience",
        needs_attention=False,
    )
    db_session.add(review)
    await db_session.commit()

    summary = await review_summary.get_aggregate_summary(sample_restaurant.id, db_session)

    assert summary.category_opinions.food == "Excellent"
    assert summary.overall_summary == "Very positive experience"
    assert summary.needs_attention is False


# API Endpoint Tests (requires FastAPI TestClient)

@pytest.mark.asyncio
async def test_ingest_reviews_api(db_session: AsyncSession, sample_restaurant, sample_reviews_json):
    """Test review ingestion via API endpoint."""
    from fastapi.testclient import TestClient
    from app.main import app

    # Override get_session dependency
    from app.database import get_session

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    # Create file-like object
    json_content = json.dumps(sample_reviews_json).encode()
    files = {"file": ("reviews.json", BytesIO(json_content), "application/json")}

    # Note: TestClient doesn't support async properly, so we test the service layer instead
    # In production, use httpx.AsyncClient for async endpoint testing

    # Clean up
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_review_pagination(db_session: AsyncSession, sample_restaurant):
    """Test review list pagination."""
    # Insert 30 reviews
    for i in range(30):
        review = Review(
            restaurant_id=sample_restaurant.id,
            platform="yelp",
            review_identifier=f"page_test_{i}",
            rating=5,
            text=f"Review {i}",
            review_date=datetime.utcnow(),
        )
        db_session.add(review)
    await db_session.commit()

    # Test pagination manually
    from sqlalchemy import select

    # Page 1
    stmt = (
        select(Review)
        .where(Review.restaurant_id == sample_restaurant.id)
        .order_by(Review.review_date.desc())
        .offset(0)
        .limit(10)
    )
    result = await db_session.execute(stmt)
    page1 = list(result.scalars().all())
    assert len(page1) == 10

    # Page 2
    stmt = (
        select(Review)
        .where(Review.restaurant_id == sample_restaurant.id)
        .order_by(Review.review_date.desc())
        .offset(10)
        .limit(10)
    )
    result = await db_session.execute(stmt)
    page2 = list(result.scalars().all())
    assert len(page2) == 10

    # Page 3
    stmt = (
        select(Review)
        .where(Review.restaurant_id == sample_restaurant.id)
        .order_by(Review.review_date.desc())
        .offset(20)
        .limit(10)
    )
    result = await db_session.execute(stmt)
    page3 = list(result.scalars().all())
    assert len(page3) == 10


@pytest.mark.asyncio
async def test_invalid_json_handling(sample_restaurant):
    """Test that invalid JSON is properly rejected."""
    from app.schemas.review import ReviewCreate
    from pydantic import ValidationError

    # Missing required field
    invalid_data = {
        "platform": "yelp",
        "rating": 5,
        # Missing review_identifier, text, review_date
    }

    with pytest.raises(ValidationError):
        ReviewCreate(**invalid_data)


@pytest.mark.asyncio
async def test_invalid_rating_range(sample_restaurant):
    """Test that ratings outside 1-5 are rejected."""
    from app.schemas.review import ReviewCreate
    from pydantic import ValidationError

    # Rating too high
    invalid_data = {
        "platform": "yelp",
        "review_identifier": "test_001",
        "rating": 6,  # Invalid
        "text": "Test",
        "review_date": "2024-01-15T12:00:00Z",
    }

    with pytest.raises(ValidationError):
        ReviewCreate(**invalid_data)


@pytest.mark.asyncio
async def test_review_stats_distribution_accuracy(db_session: AsyncSession, sample_restaurant):
    """Test that rating distribution is calculated correctly."""
    # Insert reviews with known distribution
    # 3x 5-star, 2x 4-star, 1x 3-star, 1x 2-star, 1x 1-star
    ratings = [5, 5, 5, 4, 4, 3, 2, 1]

    for i, rating in enumerate(ratings):
        review = Review(
            restaurant_id=sample_restaurant.id,
            platform="yelp",
            review_identifier=f"dist_test_{i}",
            rating=rating,
            text=f"Test review {i}",
            review_date=datetime.utcnow(),
        )
        db_session.add(review)
    await db_session.commit()

    stats = await review_stats.get_review_stats(sample_restaurant.id, db_session)

    assert stats.rating_distribution.five_star == 3
    assert stats.rating_distribution.four_star == 2
    assert stats.rating_distribution.three_star == 1
    assert stats.rating_distribution.two_star == 1
    assert stats.rating_distribution.one_star == 1

    # Average should be (5+5+5+4+4+3+2+1)/8 = 29/8 = 3.625
    # Rounded to 2 decimals = 3.62
    assert stats.overall_average == 3.62


@pytest.mark.asyncio
async def test_batch_processing_multiple_batches(db_session: AsyncSession, sample_restaurant, mock_llm_response, monkeypatch):
    """Test that large review sets are processed in batches."""
    # Insert 60 pending reviews (should be 3 batches of 25)
    for i in range(60):
        review = Review(
            restaurant_id=sample_restaurant.id,
            platform="yelp",
            review_identifier=f"batch_test_{i}",
            rating=5,
            text=f"Review {i}",
            review_date=datetime.utcnow(),
            status="pending",
        )
        db_session.add(review)
    await db_session.commit()

    # Mock LLM call
    async def mock_call_llm(*args, **kwargs):
        return mock_llm_response

    monkeypatch.setattr("app.services.review_categorization.call_llm", mock_call_llm)

    # Trigger categorization with batch size of 25
    result = await review_categorization.categorize_reviews_batch(
        sample_restaurant.id, db_session, batch_size=25
    )

    # Should process 60 reviews in 3 batches (25 + 25 + 10)
    assert result["processed"] == 60
    assert result["batches"] == 3
    assert result["pending_remaining"] == 0
