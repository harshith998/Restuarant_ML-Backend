# Review Management System - Implementation Plan

**Restaurant:** Mimosas Southern Bar and Grill (Myrtle Beach)
**Scope:** ~70 Yelp reviews, LLM-powered category analysis, Manager UI backend
**Timeline:** Parallel execution where possible

---

## 📋 Table of Contents
1. [Work Stream A: LLM Client](#stream-a-llm-client-infrastructure)
2. [Work Stream B: Database Schema](#stream-b-database-schema--models)
3. [Work Stream C: Scraper Development](#stream-c-scraper-development)
4. [Work Stream D: Review Services](#stream-d-review-services-business-logic)
5. [Work Stream E: API Endpoints](#stream-e-api-endpoints)
6. [Work Stream F: Testing](#stream-f-testing)
7. [Work Stream G: Documentation](#stream-g-documentation)
8. [Dependency Chart](#dependency-chart)
9. [Integration Points](#integration-points)

---

## 🔧 STREAM A: LLM Client Infrastructure

**Status:** 🟢 Can Start Immediately (No Dependencies)
**Estimated Complexity:** Low
**Files Created:** 1 new, 1 modified

### Purpose
Create a reusable LLM client that connects to OpenRouter (ByteDance model) for all AI-powered analysis tasks. This is a template function that will be used across the platform.

### Tasks

#### A1: Create LLM Client Module
**File:** `app/services/llm_client.py`

**Requirements:**
- Async function using `httpx` for API calls
- Configurable system prompt (parameter)
- Configurable user prompt (parameter)
- Temperature control (default 0.7)
- JSON response parsing with validation
- Retry logic (3 attempts with exponential backoff)
- Error handling and logging
- OpenRouter API integration

**Function Signature:**
```python
async def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    response_format: str = "json"  # Expect JSON responses
) -> dict
```

**Implementation Notes:**
- API Endpoint: `https://openrouter.ai/api/v1/chat/completions`
- Headers: `Authorization: Bearer {OPENROUTER_API_KEY}`
- Model: Use env var `OPENROUTER_MODEL` (e.g., `bytedance/doubao-pro-32k`)
- Timeout: 30 seconds
- Log all API calls for debugging
- Parse response as JSON, validate structure
- On error: retry 3x with 1s, 2s, 4s delays

**Error Cases to Handle:**
- Network timeout
- Invalid JSON response
- Rate limiting (429 status)
- Invalid API key (401 status)

#### A2: Update Environment Configuration
**File:** `.env.example`

**Add:**
```bash
# OpenRouter LLM Configuration
OPENROUTER_API_KEY=your_api_key_here
OPENROUTER_MODEL=bytedance-seed/seed-1.6
```

### Acceptance Criteria
- [ ] `call_llm()` successfully connects to OpenRouter
- [ ] Returns parsed JSON dict
- [ ] Handles errors gracefully with retries
- [ ] Logs requests/responses
- [ ] Can be imported: `from app.services.llm_client import call_llm`

### Testing
```python
# Manual test
result = await call_llm(
    system_prompt="You are a helpful assistant.",
    user_prompt="Say hello in JSON format: {\"message\": \"...\"}",
    temperature=0.5
)
assert "message" in result
```

---

## 🗄️ STREAM B: Database Schema & Models

**Status:** 🟢 Can Start Immediately (No Dependencies)
**Estimated Complexity:** Medium
**Files Created:** 2 new, 3 modified

### Purpose
Create database tables and Pydantic schemas for storing reviews and exposing data to API.

### Tasks

#### B1: Update Restaurant Model
**File:** `app/models/restaurant.py`

**Add Field:**
```python
yelp_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
```

**Reason:** Store Yelp business page URL for reference

#### B2: Create Review Model
**File:** `app/models/review.py` (NEW)

**Schema:**
```python
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base

class Review(Base):
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
    review_date: Mapped[datetime] = mapped_column(DateTime)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationship
    restaurant: Mapped["Restaurant"] = relationship("Restaurant", back_populates="reviews")
```

**Notes:**
- `review_identifier`: Simple unique ID (e.g., hash of text+date, or counter)
- `category_opinions`: Dict with 5 categories (food, service, atmosphere, value, cleanliness)
- `status`: Tracks processing state

#### B3: Update Restaurant Relationship
**File:** `app/models/restaurant.py`

**Add to Restaurant class:**
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.review import Review

# In Restaurant class relationships:
reviews: Mapped[List["Review"]] = relationship(
    "Review", back_populates="restaurant", cascade="all, delete-orphan"
)
```

#### B4: Create Review Schemas
**File:** `app/schemas/review.py` (NEW)

**Schemas Needed:**

```python
from __future__ import annotations
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

# For scraper JSON ingestion
class ReviewCreate(BaseModel):
    platform: str = "yelp"
    review_identifier: str
    rating: int = Field(ge=1, le=5)
    text: str
    review_date: datetime

# For API responses
class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    platform: str
    rating: int
    text: str
    review_date: datetime
    sentiment_score: float | None
    category_opinions: dict | None
    overall_summary: str | None
    needs_attention: bool
    status: str
    created_at: datetime

# Aggregate statistics (no LLM, pure SQL)
class RatingDistribution(BaseModel):
    five_star: int
    four_star: int
    three_star: int
    two_star: int
    one_star: int

class ReviewStats(BaseModel):
    """Stats computed from raw review data (no LLM)"""
    overall_average: float  # Average of all ratings
    total_reviews: int
    reviews_this_month: int
    rating_distribution: RatingDistribution

# LLM-generated category analysis
class CategoryOpinions(BaseModel):
    """Narrative statements for each category"""
    food: str
    service: str
    atmosphere: str
    value: str
    cleanliness: str

class ReviewSummary(BaseModel):
    """LLM-generated insights from review batch"""
    category_opinions: CategoryOpinions
    overall_summary: str  # 2-3 sentence summary
    needs_attention: bool  # True if negative sentiment detected
```

#### B5: Update Model Imports
**File:** `app/models/__init__.py`

**Add:**
```python
from app.models.review import Review
```

**File:** `app/main.py`

**Add to imports section (around line 21):**
```python
from app.models import (
    # ... existing imports ...
    Review,  # ADD THIS
)
```

#### B6: Create Database Migration
**Commands to run:**
```bash
# Generate migration
alembic revision --autogenerate -m "add review system"

# Review the generated migration file
# Check SQL looks correct

# Apply migration
alembic upgrade head
```

**Verify:**
- `reviews` table created with all columns
- Foreign key to `restaurants.id` exists
- Unique constraint on `review_identifier`

### Acceptance Criteria
- [ ] Review model created with all fields
- [ ] Restaurant model has `yelp_url` field
- [ ] Schemas created for all use cases
- [ ] Migration runs successfully
- [ ] Can query: `SELECT * FROM reviews;`

---

## 🕷️ STREAM C: Scraper Development

**Status:** 🟢 Can Start Immediately (No Dependencies)
**Estimated Complexity:** High
**Files Created:** 5 new

### Purpose
Selenium-based web scraper to extract 75 Yelp reviews for Mimosas Southern Bar and Grill.

### Tasks

#### C1: Create Scraper Directory Structure
**Create directories and files:**
```
/scraper/
  ├── requirements.txt
  ├── config.py
  ├── scraper.py
  ├── README.md
  └── output/
      └── .gitkeep
```

#### C2: Scraper Configuration
**File:** `scraper/config.py`

```python
"""Scraper configuration for Mimosas Southern Bar and Grill"""

# Restaurant details
RESTAURANT_NAME = "Mimosas Southern Bar and Grill"
RESTAURANT_LOCATION = "Myrtle Beach, SC"

# Yelp URL
YELP_URL = "https://www.yelp.com/biz/mimosas-myrtle-beach-2"

# Scraping settings
TARGET_REVIEW_COUNT = 75  # Number of reviews to scrape
OUTPUT_FILE = "output/reviews.json"

# Selenium settings
HEADLESS = True  # Run browser in background
TIMEOUT = 10  # Seconds to wait for elements
RETRY_ATTEMPTS = 3
```

#### C3: Scraper Requirements
**File:** `scraper/requirements.txt`

```
selenium>=4.16.0
webdriver-manager>=4.0.1
```

**Installation:**
```bash
cd scraper
pip install -r requirements.txt
```

#### C4: Implement Scraper
**File:** `scraper/scraper.py`

**Core Functionality:**

```python
import json
import hashlib
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time

from config import (
    YELP_URL,
    TARGET_REVIEW_COUNT,
    OUTPUT_FILE,
    HEADLESS,
    TIMEOUT,
    RESTAURANT_NAME
)

def setup_driver():
    """Initialize Selenium Chrome driver"""
    options = Options()
    if HEADLESS:
        options.add_argument('--headless')
    options.add_argument('--disable-bots')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def generate_review_id(text: str, date: str) -> str:
    """Generate unique review identifier from text and date"""
    combined = f"{text}_{date}"
    return f"yelp_{hashlib.md5(combined.encode()).hexdigest()[:12]}"

def scrape_yelp_reviews(driver, target_count=75):
    """Scrape reviews from Yelp"""
    driver.get(YELP_URL)
    time.sleep(3)  # Let page load

    reviews = []

    # TODO: Implement Yelp-specific scraping logic
    # - Find review elements
    # - Extract rating, text, date
    # - Handle "Read more" buttons
    # - Paginate if needed
    # - Stop at target_count

    # Example structure (adapt to actual Yelp HTML):
    # review_elements = driver.find_elements(By.CSS_SELECTOR, ".review-element-class")
    # for element in review_elements[:target_count]:
    #     rating = extract_rating(element)
    #     text = extract_text(element)
    #     date = extract_date(element)
    #     reviews.append({...})

    return reviews

def save_reviews(reviews, output_path):
    """Save reviews to JSON file"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(reviews, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(reviews)} reviews to {output_path}")

def main():
    print(f"Starting scraper for {RESTAURANT_NAME}")
    print(f"Target: {TARGET_REVIEW_COUNT} reviews")

    driver = setup_driver()

    try:
        reviews = scrape_yelp_reviews(driver, TARGET_REVIEW_COUNT)
        save_reviews(reviews, OUTPUT_FILE)
        print(f"✓ Successfully scraped {len(reviews)} reviews")
    except Exception as e:
        print(f"✗ Scraping failed: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
```

**Expected Output Format:**
```json
[
  {
    "platform": "yelp",
    "review_identifier": "yelp_a1b2c3d4e5f6",
    "rating": 5,
    "text": "Amazing southern food! The shrimp and grits were incredible and the service was top-notch. Highly recommend!",
    "review_date": "2024-01-15T00:00:00Z"
  },
  {
    "platform": "yelp",
    "review_identifier": "yelp_f6e5d4c3b2a1",
    "rating": 2,
    "text": "Service was extremely slow. Waited 45 minutes for our food and it arrived cold. Very disappointed.",
    "review_date": "2024-01-10T00:00:00Z"
  }
]
```

#### C5: Scraper Documentation
**File:** `scraper/README.md`

```markdown
# Yelp Review Scraper

Scrapes reviews from Yelp for **Mimosas Southern Bar and Grill** in Myrtle Beach.

## Setup

```bash
cd scraper
pip install -r requirements.txt
```

## Usage

```bash
python scraper.py
```

Output: `output/reviews.json`

## Configuration

Edit `config.py` to change:
- Target review count
- Output file path
- Selenium settings (headless mode, timeout)

## Output Format

JSON array with:
- `platform`: "yelp"
- `review_identifier`: Unique ID
- `rating`: 1-5 stars
- `text`: Review content
- `review_date`: ISO 8601 timestamp
```

### Acceptance Criteria
- [ ] Scraper runs without errors
- [ ] Outputs valid JSON to `scraper/output/reviews.json`
- [ ] Successfully scrapes 75 reviews (or max available)
- [ ] Each review has unique `review_identifier`
- [ ] Rating, text, and date extracted correctly
- [ ] Handles errors gracefully (retry, skip malformed)

### Testing
```bash
cd scraper
python scraper.py

# Verify output
cat output/reviews.json | python -m json.tool
```

---

## 🔄 STREAM D: Review Services (Business Logic)

**Status:** ✅ COMPLETE
**Estimated Complexity:** Medium
**Files Created:** 4 new

**IMPLEMENTATION NOTES (Completed):**
- All 4 service files created and tested
- Services properly exported in `app/services/__init__.py`
- Syntax validation passed
- Import tests successful
- Ready for Stream E integration

### Purpose
Implement business logic for ingesting reviews, computing stats, and running LLM categorization.

### Dependencies
- ✅ Stream A: `call_llm()` function exists
- ✅ Stream B: Review model and schemas exist

### Tasks

#### D1: Ingestion Service
**File:** `app/services/review_ingestion.py`

**Purpose:** Load scraped JSON into database

```python
from __future__ import annotations
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.review import Review
from app.schemas.review import ReviewCreate
import logging

logger = logging.getLogger(__name__)

async def bulk_ingest(
    restaurant_id: UUID,
    reviews: list[ReviewCreate],
    session: AsyncSession
) -> int:
    """
    Ingest reviews from scraper JSON.
    Skips duplicates by review_identifier.
    Returns count of newly added reviews.
    """
    added = 0

    for review_data in reviews:
        # Check for duplicate
        stmt = select(Review).where(
            Review.review_identifier == review_data.review_identifier
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            logger.info(f"Skipping duplicate: {review_data.review_identifier}")
            continue

        # Create new review
        review = Review(
            restaurant_id=restaurant_id,
            platform=review_data.platform,
            review_identifier=review_data.review_identifier,
            rating=review_data.rating,
            text=review_data.text,
            review_date=review_data.review_date,
            status="pending"
        )
        session.add(review)
        added += 1

    await session.commit()
    logger.info(f"Ingested {added} new reviews")
    return added
```

#### D2: Stats Service
**File:** `app/services/review_stats.py`

**Purpose:** Calculate aggregate statistics (NO LLM)

```python
from __future__ import annotations
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.review import Review
from app.schemas.review import ReviewStats, RatingDistribution

async def get_review_stats(
    restaurant_id: UUID,
    session: AsyncSession
) -> ReviewStats:
    """
    Calculate review statistics from raw data.
    No LLM calls - pure SQL aggregation.
    """

    # Overall average and count
    stmt = select(
        func.count(Review.id),
        func.avg(Review.rating)
    ).where(Review.restaurant_id == restaurant_id)

    result = await session.execute(stmt)
    total_count, avg_rating = result.one()

    # This month's count
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    stmt = select(func.count(Review.id)).where(
        Review.restaurant_id == restaurant_id,
        Review.review_date >= month_start
    )
    result = await session.execute(stmt)
    this_month = result.scalar()

    # Rating distribution
    distribution = {}
    for stars in range(1, 6):
        stmt = select(func.count(Review.id)).where(
            Review.restaurant_id == restaurant_id,
            Review.rating == stars
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
            one_star=distribution[1]
        )
    )
```

#### D3: Categorization Service
**File:** `app/services/review_categorization.py`

**Purpose:** Use LLM to analyze reviews in batches

```python
from __future__ import annotations
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.review import Review
from app.services.llm_client import call_llm
import logging

logger = logging.getLogger(__name__)

# LLM Prompts
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
    batch_size: int = 25
) -> dict:
    """
    Categorize pending reviews using LLM.
    Processes in batches of 25 reviews.
    Returns summary of processing.
    """

    # Fetch pending reviews
    stmt = select(Review).where(
        Review.restaurant_id == restaurant_id,
        Review.status == "pending"
    ).order_by(Review.review_date.desc())

    result = await session.execute(stmt)
    pending_reviews = list(result.scalars().all())

    if not pending_reviews:
        return {"processed": 0, "batches": 0, "message": "No pending reviews"}

    total_processed = 0
    batch_count = 0

    # Process in batches
    for i in range(0, len(pending_reviews), batch_size):
        batch = pending_reviews[i:i + batch_size]
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
                temperature=0.7
            )

            # Update each review in batch with same insights
            # (All reviews in batch share the same aggregate analysis)
            for review in batch:
                review.category_opinions = llm_response.get("category_opinions", {})
                review.overall_summary = llm_response.get("overall_summary", "")
                review.needs_attention = llm_response.get("needs_attention", False)
                review.sentiment_score = -0.5 if review.needs_attention else 0.5
                review.status = "categorized"

            total_processed += len(batch)
            await session.commit()

        except Exception as e:
            logger.error(f"LLM categorization failed for batch {batch_count}: {e}")
            # Continue to next batch
            continue

    return {
        "processed": total_processed,
        "batches": batch_count,
        "pending_remaining": len(pending_reviews) - total_processed
    }
```

#### D4: Summary Service
**File:** `app/services/review_summary.py`

**Purpose:** Generate aggregate summary across all reviews

```python
from __future__ import annotations
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.review import Review
from app.schemas.review import ReviewSummary, CategoryOpinions

async def get_aggregate_summary(
    restaurant_id: UUID,
    session: AsyncSession
) -> ReviewSummary:
    """
    Get aggregate summary from categorized reviews.
    Uses most recent categorization results.
    """

    # Get most recently categorized review (all in batch share same analysis)
    stmt = select(Review).where(
        Review.restaurant_id == restaurant_id,
        Review.status == "categorized",
        Review.category_opinions.isnot(None)
    ).order_by(Review.updated_at.desc()).limit(1)

    result = await session.execute(stmt)
    latest = result.scalar_one_or_none()

    if not latest:
        # No categorized reviews yet
        return ReviewSummary(
            category_opinions=CategoryOpinions(
                food="Not enough data",
                service="Not enough data",
                atmosphere="Not enough data",
                value="Not enough data",
                cleanliness="Not enough data"
            ),
            overall_summary="No reviews have been analyzed yet.",
            needs_attention=False
        )

    # Return latest categorization
    return ReviewSummary(
        category_opinions=CategoryOpinions(**latest.category_opinions),
        overall_summary=latest.overall_summary or "",
        needs_attention=latest.needs_attention
    )
```

### Acceptance Criteria
- [ ] `bulk_ingest()` successfully loads JSON reviews
- [ ] `get_review_stats()` calculates correct averages and distributions
- [ ] `categorize_reviews_batch()` calls LLM and updates reviews
- [ ] `get_aggregate_summary()` returns formatted category opinions
- [ ] All functions use async/await
- [ ] Error handling in place

### Testing
```python
# Test ingestion
reviews_data = [ReviewCreate(...), ...]
added = await bulk_ingest(restaurant_id, reviews_data, session)
assert added == len(reviews_data)

# Test stats
stats = await get_review_stats(restaurant_id, session)
assert stats.overall_average > 0

# Test categorization (requires LLM)
result = await categorize_reviews_batch(restaurant_id, session)
assert result["processed"] > 0
```

---

## 🌐 STREAM E: API Endpoints

**Status:** ✅ COMPLETE
**Estimated Complexity:** Low
**Files Created:** 1 new, 2 modified

**IMPLEMENTATION NOTES (Completed):**
- All 5 endpoints implemented and registered
- Background task properly handles session management
- Router validated with all endpoints accessible
- Integrated into main FastAPI application
- Next: Stream F (Testing)

### Purpose
Expose review functionality via REST API endpoints.

### Dependencies
- ✅ Stream D: All review services implemented

### Tasks

#### E1: Create Review API Router
**File:** `app/api/reviews.py`

```python
from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.database import get_session
from app.schemas.review import (
    ReviewRead,
    ReviewCreate,
    ReviewStats,
    ReviewSummary
)
from app.services import (
    review_ingestion,
    review_stats,
    review_categorization,
    review_summary
)

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])

@router.post("/{restaurant_id}/ingest")
async def ingest_reviews(
    restaurant_id: UUID,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    session: AsyncSession = Depends(get_session)
) -> dict:
    """
    Ingest reviews from JSON file.
    Triggers background categorization.
    """
    # Parse uploaded JSON
    content = await file.read()
    try:
        reviews_data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    # Validate and convert to schemas
    reviews = [ReviewCreate(**r) for r in reviews_data]

    # Ingest reviews
    added = await review_ingestion.bulk_ingest(restaurant_id, reviews, session)

    # Trigger categorization in background
    if background_tasks:
        background_tasks.add_task(
            review_categorization.categorize_reviews_batch,
            restaurant_id,
            session
        )

    return {
        "added": added,
        "total_submitted": len(reviews),
        "status": "categorizing" if added > 0 else "no_new_reviews"
    }

@router.get("/{restaurant_id}/stats", response_model=ReviewStats)
async def get_stats(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> ReviewStats:
    """Get aggregate review statistics (no LLM)."""
    return await review_stats.get_review_stats(restaurant_id, session)

@router.get("/{restaurant_id}/summary", response_model=ReviewSummary)
async def get_summary(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> ReviewSummary:
    """Get LLM-generated category opinions and summary."""
    return await review_summary.get_aggregate_summary(restaurant_id, session)

@router.get("/{restaurant_id}/reviews", response_model=list[ReviewRead])
async def get_reviews(
    restaurant_id: UUID,
    skip: int = 0,
    limit: int = 50,
    session: AsyncSession = Depends(get_session)
) -> list[ReviewRead]:
    """Get paginated raw reviews."""
    from sqlalchemy import select
    from app.models.review import Review

    stmt = select(Review).where(
        Review.restaurant_id == restaurant_id
    ).order_by(Review.review_date.desc()).offset(skip).limit(limit)

    result = await session.execute(stmt)
    return list(result.scalars().all())

@router.post("/{restaurant_id}/categorize")
async def trigger_categorization(
    restaurant_id: UUID,
    session: AsyncSession = Depends(get_session)
) -> dict:
    """Manually trigger LLM categorization for pending reviews."""
    result = await review_categorization.categorize_reviews_batch(
        restaurant_id, session, batch_size=25
    )
    return result
```

#### E2: Register Router
**File:** `app/api/__init__.py`

**Add:**
```python
from app.api.reviews import router as reviews_router
```

**Update `__all__`:**
```python
__all__ = [
    # ... existing routers ...
    "reviews_router",
]
```

#### E3: Include Router in Main App
**File:** `app/main.py`

**Add after line 136:**
```python
from app.api import reviews_router
app.include_router(reviews_router)
```

### Acceptance Criteria
- [ ] All endpoints accessible at `/api/v1/reviews/*`
- [ ] POST `/ingest` accepts JSON file and returns count
- [ ] GET `/stats` returns correct aggregate stats
- [ ] GET `/summary` returns LLM-generated insights
- [ ] GET `/reviews` returns paginated review list
- [ ] POST `/categorize` triggers manual LLM processing
- [ ] Background categorization works after ingest

### Testing
```bash
# Test ingest
curl -X POST http://localhost:8000/api/v1/reviews/{restaurant_id}/ingest \
  -F "file=@scraper/output/reviews.json"

# Test stats
curl http://localhost:8000/api/v1/reviews/{restaurant_id}/stats

# Test summary
curl http://localhost:8000/api/v1/reviews/{restaurant_id}/summary

# Test reviews list
curl "http://localhost:8000/api/v1/reviews/{restaurant_id}/reviews?limit=10"
```

---

## ✅ STREAM F: Testing

**Status:** ✅ COMPLETE
**Estimated Complexity:** Medium
**Files Created:** 1 new

**IMPLEMENTATION NOTES (Completed):**
- 14 comprehensive tests created and passing (100%)
- All critical paths tested with mocked LLM
- Service layer, edge cases, and integration tests
- Test execution time: <1 second
- Ready for Stream G (Documentation)

### Purpose
Comprehensive tests for review system functionality.

### Dependencies
- ✅ Stream E: All API endpoints implemented

### Tasks

#### F1: Create Test File
**File:** `tests/test_reviews.py`

```python
import pytest
from httpx import AsyncClient
from datetime import datetime
from app.models.review import Review

@pytest.fixture
def sample_review_data():
    """Sample review data for testing"""
    return {
        "platform": "yelp",
        "review_identifier": "test_review_001",
        "rating": 5,
        "text": "Amazing food and service!",
        "review_date": "2024-01-15T12:00:00Z"
    }

@pytest.fixture
def sample_reviews_json():
    """Multiple reviews for bulk testing"""
    return [
        {
            "platform": "yelp",
            "review_identifier": f"test_review_{i:03d}",
            "rating": (i % 5) + 1,
            "text": f"Review number {i}",
            "review_date": "2024-01-15T12:00:00Z"
        }
        for i in range(10)
    ]

@pytest.mark.asyncio
async def test_ingest_reviews(client: AsyncClient, restaurant, sample_reviews_json):
    """Test bulk review ingestion"""
    import json
    from io import BytesIO

    # Create file-like object
    json_content = json.dumps(sample_reviews_json).encode()
    files = {"file": ("reviews.json", BytesIO(json_content), "application/json")}

    response = await client.post(
        f"/api/v1/reviews/{restaurant.id}/ingest",
        files=files
    )

    assert response.status_code == 200
    data = response.json()
    assert data["added"] == 10
    assert data["total_submitted"] == 10

@pytest.mark.asyncio
async def test_get_stats(client: AsyncClient, restaurant, session):
    """Test review statistics calculation"""
    # Insert test reviews directly
    from app.models.review import Review

    for i in range(5):
        review = Review(
            restaurant_id=restaurant.id,
            platform="yelp",
            review_identifier=f"stat_test_{i}",
            rating=(i % 5) + 1,
            text=f"Test review {i}",
            review_date=datetime.utcnow()
        )
        session.add(review)
    await session.commit()

    response = await client.get(f"/api/v1/reviews/{restaurant.id}/stats")
    assert response.status_code == 200

    stats = response.json()
    assert stats["total_reviews"] == 5
    assert stats["overall_average"] > 0

@pytest.mark.asyncio
async def test_get_reviews_pagination(client: AsyncClient, restaurant, session):
    """Test review list pagination"""
    # Insert 30 reviews
    for i in range(30):
        review = Review(
            restaurant_id=restaurant.id,
            platform="yelp",
            review_identifier=f"page_test_{i}",
            rating=5,
            text=f"Review {i}",
            review_date=datetime.utcnow()
        )
        session.add(review)
    await session.commit()

    # Get first page
    response = await client.get(
        f"/api/v1/reviews/{restaurant.id}/reviews?limit=10&skip=0"
    )
    assert response.status_code == 200
    reviews = response.json()
    assert len(reviews) == 10

    # Get second page
    response = await client.get(
        f"/api/v1/reviews/{restaurant.id}/reviews?limit=10&skip=10"
    )
    reviews = response.json()
    assert len(reviews) == 10

@pytest.mark.asyncio
async def test_categorization_mock(client: AsyncClient, restaurant, session, monkeypatch):
    """Test categorization with mocked LLM"""
    # Insert pending review
    review = Review(
        restaurant_id=restaurant.id,
        platform="yelp",
        review_identifier="cat_test_001",
        rating=5,
        text="Great food!",
        review_date=datetime.utcnow(),
        status="pending"
    )
    session.add(review)
    await session.commit()

    # Mock LLM response
    async def mock_call_llm(*args, **kwargs):
        return {
            "category_opinions": {
                "food": "Excellent",
                "service": "Great",
                "atmosphere": "Nice",
                "value": "Good",
                "cleanliness": "Clean"
            },
            "overall_summary": "Positive feedback",
            "needs_attention": False
        }

    monkeypatch.setattr("app.services.review_categorization.call_llm", mock_call_llm)

    # Trigger categorization
    response = await client.post(f"/api/v1/reviews/{restaurant.id}/categorize")
    assert response.status_code == 200
    result = response.json()
    assert result["processed"] > 0
```

#### F2: Run Tests
```bash
pytest tests/test_reviews.py -v
```

### Acceptance Criteria
- [ ] All tests pass
- [ ] Coverage > 80% for review services
- [ ] Ingestion test validates duplicate handling
- [ ] Stats test validates correct calculations
- [ ] Categorization test uses mocked LLM

---

## 📚 STREAM G: Documentation

**Status:** 🔴 BLOCKED - Requires Stream F Complete
**Estimated Complexity:** Low
**Files Created:** 2 new, 1 modified

### Purpose
Document the complete review system for frontend developers and future maintainers.

### Dependencies
- ✅ Stream F: All tests passing

### Tasks

#### G1: Frontend Integration Guide
**File:** `FRONTEND_GUIDE.md`

```markdown
# Review Management System - Frontend Integration Guide

## Overview
Backend API for review management system. Supports ingestion, statistics, and LLM-powered category analysis.

## API Endpoints

### 1. Ingest Reviews
**POST** `/api/v1/reviews/{restaurant_id}/ingest`

Upload scraped review JSON file.

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/reviews/{restaurant_id}/ingest \
  -F "file=@reviews.json"
```

**Response:**
```json
{
  "added": 75,
  "total_submitted": 75,
  "status": "categorizing"
}
```

### 2. Get Statistics
**GET** `/api/v1/reviews/{restaurant_id}/stats`

Get aggregate review statistics (no LLM).

**Response:**
```json
{
  "overall_average": 4.2,
  "total_reviews": 75,
  "reviews_this_month": 12,
  "rating_distribution": {
    "five_star": 45,
    "four_star": 15,
    "three_star": 8,
    "two_star": 5,
    "one_star": 2
  }
}
```

### 3. Get AI Summary
**GET** `/api/v1/reviews/{restaurant_id}/summary`

Get LLM-generated category opinions.

**Response:**
```json
{
  "category_opinions": {
    "food": "Customers consistently praise the shrimp and grits as exceptional, with many noting the authentic southern flavors and generous portions.",
    "service": "Service receives mixed feedback, with some highlighting friendly staff while others mention slow response times during peak hours.",
    "atmosphere": "The casual, welcoming ambiance is frequently mentioned as perfect for family gatherings and celebrations.",
    "value": "Most reviewers feel the pricing is fair given the portion sizes and quality of food.",
    "cleanliness": "Generally positive comments about restaurant cleanliness, though a few mention restroom maintenance issues."
  },
  "overall_summary": "Mimosas receives strong praise for authentic southern cuisine, particularly seafood dishes. While the atmosphere and value are well-regarded, service consistency could be improved during busy periods.",
  "needs_attention": false
}
```

### 4. Get Reviews List
**GET** `/api/v1/reviews/{restaurant_id}/reviews?skip=0&limit=50`

Get paginated list of raw reviews.

**Response:**
```json
[
  {
    "id": "uuid",
    "platform": "yelp",
    "rating": 5,
    "text": "Amazing food!",
    "review_date": "2024-01-15T12:00:00Z",
    "sentiment_score": 0.8,
    "category_opinions": {...},
    "needs_attention": false,
    "status": "categorized",
    "created_at": "2024-01-16T10:00:00Z"
  }
]
```

### 5. Trigger Categorization
**POST** `/api/v1/reviews/{restaurant_id}/categorize`

Manually trigger LLM analysis for pending reviews.

**Response:**
```json
{
  "processed": 75,
  "batches": 3,
  "pending_remaining": 0
}
```

## UI Component Data Shapes

### Dashboard Stats Card
```typescript
interface ReviewStats {
  overall_average: number;  // e.g., 4.2
  total_reviews: number;
  reviews_this_month: number;
  rating_distribution: {
    five_star: number;
    four_star: number;
    three_star: number;
    two_star: number;
    one_star: number;
  };
}
```

### Category Insights Panel
```typescript
interface ReviewSummary {
  category_opinions: {
    food: string;
    service: string;
    atmosphere: string;
    value: string;
    cleanliness: string;
  };
  overall_summary: string;
  needs_attention: boolean;
}
```

## Workflow

1. **Scrape Reviews**: Run scraper to generate JSON file
2. **Ingest**: Upload JSON via `/ingest` endpoint
3. **Auto-Categorize**: LLM runs in background
4. **Display Stats**: Fetch `/stats` for dashboard
5. **Show Insights**: Fetch `/summary` for manager view
```

#### G2: Update Progress Tracker
**File:** `PROGRESS.md`

**Add section:**
```markdown
### Review Management System
- [x] Database schema (Review model)
- [x] LLM client infrastructure (OpenRouter integration)
- [x] Yelp scraper (Selenium-based)
- [x] Review services (ingestion, stats, categorization, summary)
- [x] API endpoints (ingest, stats, summary, list)
- [x] Tests (comprehensive coverage)
- [x] Documentation (FRONTEND_GUIDE.md)

**Features:**
- Scrapes 75 Yelp reviews for Mimosas Southern Bar and Grill
- LLM-powered category analysis (5 categories: food, service, atmosphere, value, cleanliness)
- Aggregate statistics (average rating, distribution)
- Manager-friendly narrative insights
```

#### G3: Scraper Documentation (if not done in Stream C)
Ensure `scraper/README.md` exists with usage instructions.

### Acceptance Criteria
- [ ] `FRONTEND_GUIDE.md` complete with all endpoints
- [ ] `PROGRESS.md` updated
- [ ] All documentation accurate and tested

---

## 📊 Dependency Chart

```
┌─────────────────────────────────────────────────────────────┐
│                    PARALLEL PHASE                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Stream A          Stream B          Stream C              │
│  (LLM Client)      (Database)        (Scraper)             │
│  ↓                 ↓                 ↓                      │
│  ✓ Complete        ✓ Complete        ✓ Complete            │
│                                                             │
└──────────────┬──────────┬────────────────────────────────────┘
               │          │
               └────┬─────┘
                    ↓
            ┌───────────────┐
            │   Stream D    │
            │  (Services)   │
            └───────┬───────┘
                    ↓
            ┌───────────────┐
            │   Stream E    │
            │     (API)     │
            └───────┬───────┘
                    ↓
            ┌───────────────┐
            │   Stream F    │
            │   (Testing)   │
            └───────┬───────┘
                    ↓
            ┌───────────────┐
            │   Stream G    │
            │     (Docs)    │
            └───────────────┘
```

**Critical Path:** A+B → D → E → F → G
**Parallel Work:** A, B, C can all run simultaneously

---

## 🔗 Integration Points

### Between Streams

**A → D:** LLM Client used by Categorization Service
```python
from app.services.llm_client import call_llm
# Used in: review_categorization.py
```

**B → D:** Models and Schemas used by all Services
```python
from app.models.review import Review
from app.schemas.review import ReviewStats, ReviewSummary
# Used in: all service files
```

**C → E:** Scraper JSON ingested via API
```bash
# Output: scraper/output/reviews.json
# Endpoint: POST /api/v1/reviews/{id}/ingest
```

**D → E:** Services called by API endpoints
```python
from app.services import review_ingestion, review_stats
# Used in: reviews.py router
```

**E → F:** API endpoints tested
```python
# Tests call endpoints via AsyncClient
```

---

## ⚙️ Environment Setup

### Required Environment Variables
```bash
# .env file
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/restaurant_db
OPENROUTER_API_KEY=your_api_key_here
OPENROUTER_MODEL=bytedance-seed/seed-1.6
```

### Installation Commands
```bash
# Main app dependencies
pip install -r requirements.txt

# Scraper dependencies (separate)
cd scraper
pip install -r requirements.txt
```

### Database Setup
```bash
# Start PostgreSQL
docker-compose up -d db

# Run migrations
alembic upgrade head
```

---

## 🎯 Final Deliverables Checklist

- [ ] **Stream A**: LLM client working with OpenRouter
- [ ] **Stream B**: Review model migrated to database
- [ ] **Stream C**: Scraper outputs 75 Yelp reviews to JSON
- [ ] **Stream D**: All 4 services implemented and tested
- [ ] **Stream E**: 5 API endpoints accessible
- [ ] **Stream F**: Test suite passing (>80% coverage)
- [ ] **Stream G**: Frontend guide and documentation complete

---

## 📞 Support & Questions

If stuck, check:
1. **COMMON_ISSUES.md** - Known problems and solutions
2. **CLAUDE.md** - Code standards and patterns
3. **PRD.md** - Original requirements

For new issues, add to `COMMON_ISSUES.md` for future reference.

---

**End of Plan**
