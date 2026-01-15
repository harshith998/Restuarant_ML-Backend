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
