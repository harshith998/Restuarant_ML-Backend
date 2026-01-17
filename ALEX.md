# ALEX.md - Review Management Feature Guide

## Overview

Build a review management system that aggregates reviews from platforms (Yelp, Google, Opentable), categorizes them with AI, and provides analytics. See the UI mockups in the project for visual reference.

**5 Services to Build:**
| # | Service | LLM? | Purpose |
|---|---------|------|---------|
| 1 | Review Categorization | Yes | Analyze sentiment, extract categories, flag "needs attention" |
| 2 | Review Ranking | No | Sort by recency, negativity, rating |
| 3 | AI Summary | Yes | Generate "What's Working", "Needs Attention", "Recommended Actions" |
| 4 | Platform Stats | No | Rating distribution, averages, counts |
| 5 | Review Management | No | Clear/dismiss, mark responded |

---

## Database Models

Create in `app/models/review.py`:

```python
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, Text, ForeignKey, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
import enum

from app.database import Base

class Platform(str, enum.Enum):
    GOOGLE = "google"
    YELP = "yelp"
    OPENTABLE = "opentable"

class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    NEEDS_RESPONSE = "needs_response"
    RESPONDED = "responded"
    DISMISSED = "dismissed"

class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id", ondelete="CASCADE"))

    # Review data
    platform: Mapped[Platform] = mapped_column(Enum(Platform))
    platform_review_id: Mapped[str] = mapped_column(String(255), unique=True)  # Dedup key
    author_name: Mapped[str] = mapped_column(String(255))
    rating: Mapped[int] = mapped_column(Integer)  # 1-5
    text: Mapped[str] = mapped_column(Text)
    review_date: Mapped[datetime] = mapped_column(DateTime)

    # AI categorization (populated by Service 1)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # -1.0 to 1.0
    categories: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {"food": 0.8, "service": -0.5, ...}
    needs_attention: Mapped[bool] = mapped_column(Boolean, default=False)

    # Status
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

Add to `app/models/__init__.py`:
```python
from app.models.review import Review, Platform, ReviewStatus
```

---

## Schemas

Create `app/schemas/review.py`:

```python
from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from enum import Enum

class Platform(str, Enum):
    GOOGLE = "google"
    YELP = "yelp"
    OPENTABLE = "opentable"

class ReviewStatus(str, Enum):
    PENDING = "pending"
    NEEDS_RESPONSE = "needs_response"
    RESPONDED = "responded"
    DISMISSED = "dismissed"

# Input
class ReviewCreate(BaseModel):
    platform: Platform
    platform_review_id: str
    author_name: str
    rating: int = Field(ge=1, le=5)
    text: str
    review_date: datetime

class ReviewBulkCreate(BaseModel):
    reviews: list[ReviewCreate]

# Output
class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    platform: Platform
    author_name: str
    rating: int
    text: str
    review_date: datetime
    sentiment_score: float | None
    categories: dict | None
    needs_attention: bool
    status: ReviewStatus
    created_at: datetime

# Stats
class RatingDistribution(BaseModel):
    five_star: int
    four_star: int
    three_star: int
    two_star: int
    one_star: int

class PlatformRating(BaseModel):
    platform: Platform
    average: float
    count: int

class ReviewStats(BaseModel):
    overall_average: float
    total_reviews: int
    reviews_this_month: int
    rating_distribution: RatingDistribution
    by_platform: list[PlatformRating]

# AI Summary
class ReviewSummary(BaseModel):
    summary_text: str
    whats_working: list[str]
    needs_attention: list[str]
    recommended_actions: list[str]
```

---

## Services

### Service 1: Categorization (LLM)

Create `app/services/review_categorization.py`:

```python
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.review import Review, ReviewStatus

# Use your preferred LLM - OpenAI, Anthropic, Ollama, etc.
# Abstract it so you can swap providers

async def categorize_review(review: Review, session: AsyncSession) -> Review:
    """
    Call LLM to analyze review text.
    Returns sentiment_score (-1 to 1), categories dict, needs_attention bool.
    """
    # TODO: Implement LLM call
    # Prompt should extract:
    # - Overall sentiment (-1.0 to 1.0)
    # - Category scores: food, service, ambiance, value, wait_time, cleanliness
    # - needs_attention: True if negative sentiment or complaint

    prompt = f"""Analyze this restaurant review and return JSON:

Review: "{review.text}"
Rating: {review.rating}/5

Return: {{"sentiment_score": float, "categories": {{"food": float, "service": float, ...}}, "needs_attention": bool}}
"""

    # response = await llm_client.complete(prompt)
    # parsed = json.loads(response)

    # review.sentiment_score = parsed["sentiment_score"]
    # review.categories = parsed["categories"]
    # review.needs_attention = parsed["needs_attention"]
    # review.status = ReviewStatus.NEEDS_RESPONSE if parsed["needs_attention"] else ReviewStatus.PENDING

    return review

async def categorize_all_pending(restaurant_id: str, session: AsyncSession):
    """Batch categorize all uncategorized reviews."""
    stmt = select(Review).where(
        Review.restaurant_id == restaurant_id,
        Review.sentiment_score.is_(None)
    )
    result = await session.execute(stmt)
    reviews = result.scalars().all()

    for review in reviews:
        await categorize_review(review, session)

    await session.commit()
```

### Service 2: Ranking (No LLM)

Create `app/services/review_ranking.py`:

```python
from __future__ import annotations
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.models.review import Review

async def get_ranked_reviews(
    restaurant_id: str,
    session: AsyncSession,
    filter_type: str = "all",  # all, needs_attention, positive
    limit: int = 50
) -> list[Review]:
    """
    Rank reviews by: recency, negativity (needs_attention first), then rating.
    """
    stmt = select(Review).where(Review.restaurant_id == restaurant_id)

    if filter_type == "needs_attention":
        stmt = stmt.where(Review.needs_attention == True)
    elif filter_type == "positive":
        stmt = stmt.where(Review.rating >= 4, Review.needs_attention == False)

    # Order: needs_attention first, then by recency
    stmt = stmt.order_by(
        desc(Review.needs_attention),
        desc(Review.review_date)
    ).limit(limit)

    result = await session.execute(stmt)
    return list(result.scalars().all())
```

### Service 3: AI Summary (LLM)

Create `app/services/review_summary.py`:

```python
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from app.models.review import Review
from app.schemas.review import ReviewSummary

async def generate_summary(restaurant_id: str, session: AsyncSession) -> ReviewSummary:
    """
    Aggregate recent reviews and generate AI summary.
    """
    # Get last 30 days of reviews
    since = datetime.utcnow() - timedelta(days=30)
    stmt = select(Review).where(
        Review.restaurant_id == restaurant_id,
        Review.review_date >= since
    )
    result = await session.execute(stmt)
    reviews = result.scalars().all()

    # Build context for LLM
    review_texts = [f"[{r.rating}/5] {r.text}" for r in reviews]

    prompt = f"""Based on these {len(reviews)} recent restaurant reviews, provide:
1. A 2-3 sentence summary
2. 3 things that are working well
3. 3 things that need attention
4. 3 recommended actions

Reviews:
{chr(10).join(review_texts[:20])}  # Limit context size

Return JSON: {{"summary_text": str, "whats_working": [str], "needs_attention": [str], "recommended_actions": [str]}}
"""

    # TODO: Call LLM and parse response
    # response = await llm_client.complete(prompt)

    return ReviewSummary(
        summary_text="...",
        whats_working=["..."],
        needs_attention=["..."],
        recommended_actions=["..."]
    )
```

### Service 4: Platform Stats (No LLM)

Create `app/services/review_stats.py`:

```python
from __future__ import annotations
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.review import Review, Platform
from app.schemas.review import ReviewStats, RatingDistribution, PlatformRating

async def get_review_stats(restaurant_id: str, session: AsyncSession) -> ReviewStats:
    """Calculate all review statistics."""

    # Total + average
    stmt = select(func.count(), func.avg(Review.rating)).where(
        Review.restaurant_id == restaurant_id
    )
    result = await session.execute(stmt)
    total, avg = result.one()

    # This month
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
    stmt = select(func.count()).where(
        Review.restaurant_id == restaurant_id,
        Review.review_date >= month_start
    )
    result = await session.execute(stmt)
    this_month = result.scalar()

    # Rating distribution
    distribution = {}
    for stars in range(1, 6):
        stmt = select(func.count()).where(
            Review.restaurant_id == restaurant_id,
            Review.rating == stars
        )
        result = await session.execute(stmt)
        distribution[stars] = result.scalar()

    # By platform
    platforms = []
    for platform in Platform:
        stmt = select(func.count(), func.avg(Review.rating)).where(
            Review.restaurant_id == restaurant_id,
            Review.platform == platform
        )
        result = await session.execute(stmt)
        count, platform_avg = result.one()
        if count > 0:
            platforms.append(PlatformRating(
                platform=platform,
                average=round(platform_avg, 1),
                count=count
            ))

    return ReviewStats(
        overall_average=round(avg or 0, 1),
        total_reviews=total or 0,
        reviews_this_month=this_month or 0,
        rating_distribution=RatingDistribution(
            five_star=distribution[5],
            four_star=distribution[4],
            three_star=distribution[3],
            two_star=distribution[2],
            one_star=distribution[1]
        ),
        by_platform=platforms
    )
```

### Service 5: Review Management (No LLM)

Create `app/services/review_management.py`:

```python
from __future__ import annotations
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.review import Review, ReviewStatus

async def mark_responded(review_id: UUID, session: AsyncSession) -> Review:
    stmt = select(Review).where(Review.id == review_id)
    result = await session.execute(stmt)
    review = result.scalar_one()
    review.status = ReviewStatus.RESPONDED
    await session.commit()
    return review

async def dismiss_review(review_id: UUID, session: AsyncSession) -> None:
    stmt = select(Review).where(Review.id == review_id)
    result = await session.execute(stmt)
    review = result.scalar_one()
    review.status = ReviewStatus.DISMISSED
    await session.commit()

async def bulk_ingest(restaurant_id: UUID, reviews: list, session: AsyncSession) -> int:
    """Ingest reviews, skip duplicates by platform_review_id."""
    added = 0
    for r in reviews:
        # Check duplicate
        stmt = select(Review).where(Review.platform_review_id == r.platform_review_id)
        result = await session.execute(stmt)
        if result.scalar_one_or_none():
            continue

        review = Review(
            restaurant_id=restaurant_id,
            **r.model_dump()
        )
        session.add(review)
        added += 1

    await session.commit()
    return added
```

---

## API Routes

Create `app/api/reviews.py`:

```python
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.review import ReviewRead, ReviewBulkCreate, ReviewStats, ReviewSummary
from app.services import review_ranking, review_stats, review_summary, review_management, review_categorization

router = APIRouter(prefix="/reviews", tags=["reviews"])

@router.post("/{restaurant_id}/ingest")
async def ingest_reviews(
    restaurant_id: UUID,
    data: ReviewBulkCreate,
    session: AsyncSession = Depends(get_session)
) -> dict:
    """Bulk ingest reviews from platform APIs."""
    added = await review_management.bulk_ingest(restaurant_id, data.reviews, session)
    # Trigger categorization in background
    await review_categorization.categorize_all_pending(str(restaurant_id), session)
    return {"added": added}

@router.get("/{restaurant_id}", response_model=list[ReviewRead])
async def get_reviews(
    restaurant_id: UUID,
    filter: str = Query("all", regex="^(all|needs_attention|positive)$"),
    session: AsyncSession = Depends(get_session)
) -> list[ReviewRead]:
    """Get reviews with optional filter."""
    return await review_ranking.get_ranked_reviews(str(restaurant_id), session, filter)

@router.get("/{restaurant_id}/stats", response_model=ReviewStats)
async def get_stats(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> ReviewStats:
    """Get review statistics."""
    return await review_stats.get_review_stats(str(restaurant_id), session)

@router.get("/{restaurant_id}/summary", response_model=ReviewSummary)
async def get_summary(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> ReviewSummary:
    """Get AI-generated review summary."""
    return await review_summary.generate_summary(str(restaurant_id), session)

@router.post("/{review_id}/respond", response_model=ReviewRead)
async def mark_responded(
    review_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> ReviewRead:
    """Mark review as responded."""
    return await review_management.mark_responded(review_id, session)

@router.delete("/{review_id}")
async def dismiss(
    review_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> dict:
    """Dismiss/clear a review."""
    await review_management.dismiss_review(review_id, session)
    return {"status": "dismissed"}
```

Register in `app/main.py`:
```python
from app.api.reviews import router as reviews_router
app.include_router(reviews_router, prefix="/api/v1")
```

---

## Curl Examples

```bash
# Ingest reviews
curl -X POST http://localhost:8000/api/v1/reviews/{restaurant_id}/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "reviews": [
      {
        "platform": "google",
        "platform_review_id": "abc123",
        "author_name": "Mike T.",
        "rating": 2,
        "text": "Service was extremely slow...",
        "review_date": "2024-01-08T12:00:00Z"
      }
    ]
  }'

# Get reviews (filtered)
curl "http://localhost:8000/api/v1/reviews/{restaurant_id}?filter=needs_attention"

# Get stats
curl http://localhost:8000/api/v1/reviews/{restaurant_id}/stats

# Get AI summary
curl http://localhost:8000/api/v1/reviews/{restaurant_id}/summary

# Mark responded
curl -X POST http://localhost:8000/api/v1/reviews/{review_id}/respond

# Dismiss
curl -X DELETE http://localhost:8000/api/v1/reviews/{review_id}
```

---

## Testing

Create `tests/test_reviews.py` - follow patterns in existing tests:

```python
import pytest
from httpx import AsyncClient

@pytest.fixture
def sample_reviews():
    return [
        {"platform": "google", "platform_review_id": "g1", "author_name": "Test User",
         "rating": 5, "text": "Great food!", "review_date": "2024-01-01T00:00:00Z"},
        {"platform": "yelp", "platform_review_id": "y1", "author_name": "Another User",
         "rating": 2, "text": "Slow service", "review_date": "2024-01-02T00:00:00Z"},
    ]

@pytest.mark.asyncio
async def test_ingest_reviews(client: AsyncClient, restaurant, sample_reviews):
    response = await client.post(
        f"/api/v1/reviews/{restaurant.id}/ingest",
        json={"reviews": sample_reviews}
    )
    assert response.status_code == 200
    assert response.json()["added"] == 2

@pytest.mark.asyncio
async def test_get_reviews_filtered(client: AsyncClient, restaurant):
    response = await client.get(
        f"/api/v1/reviews/{restaurant.id}?filter=needs_attention"
    )
    assert response.status_code == 200
```

---

## Best Practices Reminder

1. **Follow existing patterns** - Look at `app/services/waiter.py` and `app/api/tables.py` for reference
2. **Async everywhere** - All DB operations use `await`
3. **Type hints** - Use `from __future__ import annotations`
4. **Multi-tenant** - Always filter by `restaurant_id`
5. **Pydantic validation** - Validate at API boundary
6. **LLM abstraction** - Create a base class so you can swap providers

---

## Deliverables Checklist

- [ ] `app/models/review.py` - Review model
- [ ] `app/schemas/review.py` - Pydantic schemas
- [ ] `app/services/review_categorization.py` - Service 1 (LLM)
- [ ] `app/services/review_ranking.py` - Service 2
- [ ] `app/services/review_summary.py` - Service 3 (LLM)
- [ ] `app/services/review_stats.py` - Service 4
- [ ] `app/services/review_management.py` - Service 5
- [ ] `app/api/reviews.py` - API routes
- [ ] `tests/test_reviews.py` - Tests
- [ ] Alembic migration: `alembic revision --autogenerate -m "add reviews"`
- [ ] **Create `FRONTEND_GUIDE.md`** when backend is complete

---

## When Done

Create `FRONTEND_GUIDE.md` documenting:
- All API endpoints with request/response examples
- WebSocket events (if implemented)
- Expected data shapes for UI components
