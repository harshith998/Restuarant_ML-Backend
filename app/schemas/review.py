from __future__ import annotations

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


# For scraper JSON ingestion
class ReviewCreate(BaseModel):
    """Schema for creating a new review from scraped data."""
    platform: str = "yelp"
    review_identifier: str
    rating: int = Field(ge=1, le=5)
    text: str
    review_date: datetime


# For API responses
class ReviewRead(BaseModel):
    """Schema for reading review data via API."""
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
    """Distribution of ratings across 1-5 stars."""
    five_star: int
    four_star: int
    three_star: int
    two_star: int
    one_star: int


class ReviewStats(BaseModel):
    """Stats computed from raw review data (no LLM)."""
    overall_average: float  # Average of all ratings
    total_reviews: int
    reviews_this_month: int
    rating_distribution: RatingDistribution


# LLM-generated category analysis
class CategoryOpinions(BaseModel):
    """Narrative statements for each category."""
    food: str
    service: str
    atmosphere: str
    value: str
    cleanliness: str


class ReviewSummary(BaseModel):
    """LLM-generated insights from review batch."""
    category_opinions: CategoryOpinions
    overall_summary: str  # 2-3 sentence summary
    needs_attention: bool  # True if negative sentiment detected


# API response schemas
class IngestResponse(BaseModel):
    """Response from review ingestion endpoint."""
    added: int
    total_submitted: int
    status: str


class CategorizationResponse(BaseModel):
    """Response from categorization endpoint."""
    processed: int
    batches: int
    pending_remaining: int
