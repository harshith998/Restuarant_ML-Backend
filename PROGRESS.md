# Progress Tracking

## Current Phase
Phase 1: PostgreSQL Schema + Core Models - **COMPLETE**

## Directory Structure

```
Restaurant_ML-Backend/
├── app/                    # <-- ALL NEW CODE GOES HERE
│   ├── main.py             # FastAPI entry point
│   ├── config.py           # Pydantic settings
│   ├── database.py         # Async SQLAlchemy
│   ├── models/             # SQLAlchemy ORM models (13 tables)
│   ├── schemas/            # Pydantic request/response schemas
│   ├── ml/                 # ML services (classifier + crop service)
│   ├── api/                # API routes (Phase 2+)
│   └── services/           # Business logic (Phase 2+)
│
├── tests/                  # Pytest tests with realistic fixtures
├── alembic/                # Database migrations
├── weights/                # ML model weights (DINOv3)
│
├── _legacy_poc/            # ⚠️ REFERENCE ONLY - DO NOT MODIFY
│   └── (old POC code for reference)
│
├── PROGRESS.md             # This file - handoff documentation
├── COMMON_ISSUES.md        # Known issues and solutions
├── PRD.md                  # Product requirements
└── SERVICES.md             # External service specs
```

**⚠️ IMPORTANT:** The `_legacy_poc/` folder is the original proof-of-concept.
It is kept for reference only. **DO NOT modify files in this folder.**
All new development happens in the `app/` directory.

## Completed

### Phase 1 Core
- [x] Documentation setup (PROGRESS.md, COMMON_ISSUES.md)
- [x] Project structure (`app/`, `alembic/`, `tests/`)
- [x] Docker Compose for PostgreSQL
- [x] Requirements.txt and .env.example
- [x] Database connection (`app/database.py`, `app/config.py`)
- [x] SQLAlchemy models (all 13 tables)
- [x] Pydantic schemas (all entities)
- [x] Tests with realistic mock data (36 passing)
- [x] FastAPI main.py with health endpoints
- [x] Alembic migration setup

### ML Services (`app/ml/`)
- [x] `inference.py` - DINOv3 table classifier
- [x] `classifier_api.py` - `/ml/predict` endpoint
- [x] `crop_service.py` - Camera management with:
  - JSON state registry
  - Frame capture (HTTP URLs + local files)
  - Axis-aligned crop extraction from rotated bboxes
  - Retry with exponential backoff
  - In-flight limiting per camera
  - Periodic scheduler for classifier dispatch
- [x] `crop_api.py` - `/crops/*` endpoints

### Maintenance
- [x] Fixed mutable SQLAlchemy defaults for JSON columns
- [x] Normalized table list responses and async delete usage

### Review Management System - Stream A: LLM Client (COMPLETE)
- [x] `app/services/llm_client.py` - OpenRouter API integration
  - Async function `call_llm()` with configurable prompts and temperature
  - JSON response parsing with validation
  - Retry logic (3 attempts with exponential backoff: 1s, 2s, 4s)
  - Comprehensive error handling (timeout, auth, rate limit, parsing)
  - Request logging for debugging
  - Custom exception classes (LLMError, LLMTimeoutError, LLMAuthError, etc.)
- [x] Environment configuration for OpenRouter
  - `.env.local` - Contains API key: `OPENROUTER_API_KEY`
  - `.env.example` - Template with placeholder values
  - Model: `bytedance-seed/seed-1.6`
- [x] Test scripts
  - `test_llm_client.py` - Full integration test (requires app dependencies)
  - `test_llm_standalone.py` - Minimal standalone test (only needs httpx + dotenv)

### Review Management System - Stream B: Database Schema (COMPLETE)
- [x] `app/models/review.py` - Review model with all fields
  - Primary key (UUID), foreign key to restaurants
  - Scraped data fields (platform, review_identifier, rating, text, review_date)
  - LLM-generated fields (sentiment_score, category_opinions, overall_summary, needs_attention)
  - Processing status tracking (pending/categorized/dismissed)
  - Timestamps (created_at, updated_at)
- [x] `app/schemas/review.py` - Pydantic schemas
  - ReviewCreate - For scraper JSON ingestion
  - ReviewRead - For API responses
  - RatingDistribution - Star distribution (1-5)
  - ReviewStats - Aggregate statistics
  - CategoryOpinions - Five category narratives
  - ReviewSummary - LLM-generated insights
- [x] Database migration
  - Alembic migration created and applied
  - Review table with all columns and constraints

### Review Management System - Stream D: Review Services (COMPLETE)
- [x] `app/services/review_ingestion.py` - Bulk review ingestion
  - Function: `bulk_ingest(restaurant_id, reviews, session)`
  - Skips duplicates by review_identifier
  - Returns count of newly added reviews
  - Comprehensive logging
- [x] `app/services/review_stats.py` - SQL-based statistics
  - Function: `get_review_stats(restaurant_id, session)`
  - Calculates overall average, total count, this month count
  - Rating distribution across 1-5 stars
  - Pure SQL aggregation (no LLM calls)
- [x] `app/services/review_categorization.py` - LLM categorization
  - Function: `categorize_reviews_batch(restaurant_id, session, batch_size=25)`
  - Processes pending reviews in batches
  - Uses LLM to generate category opinions (food, service, atmosphere, value, cleanliness)
  - Updates reviews with sentiment scores and needs_attention flags
  - Error handling with batch-level retries
- [x] `app/services/review_summary.py` - Aggregate summary
  - Function: `get_aggregate_summary(restaurant_id, session)`
  - Retrieves most recent categorization results
  - Returns formatted CategoryOpinions and overall summary
  - Handles case when no reviews are categorized yet
- [x] Updated `app/services/__init__.py` to export review services

### Review Management System - Stream E: API Endpoints (COMPLETE)
- [x] `app/api/reviews.py` - REST API router with 5 endpoints
  - POST `/{restaurant_id}/ingest` - Upload JSON reviews file
    - Validates JSON format and review schemas
    - Triggers background LLM categorization
    - Returns count of newly added reviews
  - GET `/{restaurant_id}/stats` - Aggregate statistics
    - Returns overall average, total count, this month count
    - Rating distribution (1-5 stars)
    - No LLM calls, pure SQL
  - GET `/{restaurant_id}/summary` - LLM-generated insights
    - Returns category opinions (food, service, atmosphere, value, cleanliness)
    - Overall summary and needs_attention flag
  - GET `/{restaurant_id}/reviews` - Paginated review list
    - Supports skip/limit pagination
    - Returns full review objects with LLM data
  - POST `/{restaurant_id}/categorize` - Manual LLM trigger
    - Processes pending reviews in batches
    - Returns processing summary
- [x] Background task implementation for async categorization
  - Uses `get_session_context()` to create new session
  - Handles errors gracefully with logging
- [x] Updated `app/api/__init__.py` to export reviews_router
- [x] Updated `app/main.py` to include reviews_router
- [x] All endpoints validated and registered at `/api/v1/reviews/*`

### Review Management System - Stream F: Testing (COMPLETE)
- [x] `tests/test_reviews.py` - Comprehensive test suite (14 tests, 100% passing)
  - **Service Layer Tests (8 tests)**
    - test_bulk_ingest_new_reviews - Validates ingestion of new reviews
    - test_bulk_ingest_duplicate_handling - Ensures duplicates are skipped
    - test_get_review_stats_empty - Stats with zero reviews
    - test_get_review_stats_with_reviews - Accurate average and distribution
    - test_categorize_reviews_batch_no_pending - Handles empty queue
    - test_categorize_reviews_batch_with_mock - LLM categorization (mocked)
    - test_get_aggregate_summary_no_data - Default response when no data
    - test_get_aggregate_summary_with_data - Returns categorized insights
  - **Edge Case Tests (3 tests)**
    - test_invalid_json_handling - Pydantic validation for malformed data
    - test_invalid_rating_range - Rejects ratings outside 1-5
    - test_review_stats_distribution_accuracy - Precise distribution calculation
  - **Integration Tests (3 tests)**
    - test_ingest_reviews_api - API endpoint integration
    - test_review_pagination - Multi-page navigation
    - test_batch_processing_multiple_batches - Handles 60 reviews in 3 batches
- [x] All tests use mocked LLM calls for deterministic results
- [x] Tests follow existing codebase patterns (async, fixtures, realistic scenarios)
- [x] All 14 tests passing in <1 second
- [x] Test execution: `pytest tests/test_reviews.py -v`

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Main API (app/)                          │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │   Models    │  │   Schemas    │  │    API Routes    │   │
│  │ (13 tables) │  │  (Pydantic)  │  │   (Phase 2)      │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              ML Services (app/ml/)                   │   │
│  │  • inference.py - DINOv3 classifier                 │   │
│  │  • classifier_api.py - /ml/predict endpoint         │   │
│  │  • crop_service.py - Camera management              │   │
│  │  • crop_api.py - /crops/* endpoints                 │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                     webhooks │ ML state updates
                              ▼
                    ┌──────────────────┐
                    │  External POS    │
                    │    Systems       │
                    └──────────────────┘
```

## Files Created

### Core Application
- `app/__init__.py`
- `app/main.py` - FastAPI app with ML integration
- `app/config.py` - Pydantic settings
- `app/database.py` - Async SQLAlchemy setup

### SQLAlchemy Models (13 tables)
- `app/models/__init__.py`
- `app/models/restaurant.py`
- `app/models/section.py`
- `app/models/table.py`
- `app/models/waiter.py`
- `app/models/shift.py`
- `app/models/waitlist.py`
- `app/models/visit.py`
- `app/models/menu.py`
- `app/models/metrics.py`

### Pydantic Schemas
- `app/schemas/__init__.py`
- `app/schemas/restaurant.py`
- `app/schemas/section.py`
- `app/schemas/table.py`
- `app/schemas/waiter.py`
- `app/schemas/shift.py`
- `app/schemas/waitlist.py`
- `app/schemas/visit.py`
- `app/schemas/menu.py`
- `app/schemas/routing.py`

### ML Services
- `app/ml/__init__.py`
- `app/ml/inference.py` - DINOv3 table classifier
- `app/ml/classifier_api.py` - ML prediction endpoints
- `app/ml/crop_service.py` - Camera/crop management
- `app/ml/crop_api.py` - Crop management endpoints

### Tests
- `tests/__init__.py`
- `tests/conftest.py` - Fixtures with realistic restaurant data
- `tests/test_models.py` - SQLAlchemy model tests
- `tests/test_schemas.py` - Pydantic validation tests
- `pytest.ini` - Pytest configuration

### Infrastructure
- `docker-compose.yml` - PostgreSQL + optional pgAdmin
- `requirements.txt` - All dependencies
- `.env.example` - Environment template
- `alembic.ini` - Alembic configuration
- `alembic/env.py` - Async migration environment
- `alembic/script.py.mako` - Migration template
- `weights/` - ML model weights (copied from POC)

## Running the Application

```bash
# Install dependencies
pip3 install -r requirements.txt

# Run tests
pytest

# Start PostgreSQL
docker-compose up -d db

# Copy env file
cp .env.example .env

# Run server (without ML)
uvicorn app.main:app --reload

# Run server (with ML enabled)
ML_ENABLED=true uvicorn app.main:app --reload
```

## Next Steps for Phase 2

1. **Routing API Endpoints** (`app/api/routing.py`)
   - `POST /api/v1/restaurants/{id}/route` - Route party to table
   - `POST /api/v1/restaurants/{id}/tables/{table_id}/seat` - Seat party
   - `POST /api/v1/restaurants/{id}/mode` - Switch routing mode

2. **Routing Service** (`app/services/router.py`)
   - Port algorithm from POC `_legacy_poc/table_router.py`
   - Implement waiter priority scoring
   - Add recency penalty (soft no-double-seat)

3. **State Management Endpoints** (`app/api/state.py`)
   - Floor status endpoint
   - Table state updates
   - Waiter clock in/out/break

## Notes for Next Agent

- All 36 tests passing
- ML services in `app/ml/` - enable with `ML_ENABLED=true`
- **POC code in `_legacy_poc/` is reference only - do not modify**
- Use JSON instead of JSONB for SQLite test compatibility
- Reference PRD.md Section 4.2 for routing algorithm details

## Phase Overview

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | PostgreSQL Schema + Core Models | **COMPLETE** |
| 2 | Routing API Endpoints | Next |
| 3 | State + Waitlist Endpoints | Pending |
| 4 | Analytics Endpoints | Pending |
| 5 | Webhooks (ML/POS) | Pending |
| 6 | WebSocket Layer | Pending |
