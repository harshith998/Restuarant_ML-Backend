# Progress Tracking

## Quick Start

```bash
# 1. Start PostgreSQL database
docker-compose up -d db

# 2. Create virtual environment (first time only)
python3 -m venv .venv

# 3. Activate virtual environment
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Copy environment file (first time only)
cp .env.example .env

# 6. Run database migrations
alembic upgrade head

# 7. Start the server
uvicorn app.main:app --reload

# Server runs at http://localhost:8000
# API docs at http://localhost:8000/docs
# Health check at http://localhost:8000/healthz
```

**With ML enabled:**
```bash
ML_ENABLED=true uvicorn app.main:app --reload
```

---

## Current Phase
Phase 1: PostgreSQL Schema + Core Models - **COMPLETE**
Phase 2: Waiter Intelligence System - **COMPLETE**
Phase 3: Scheduling System (Agent 1) - **COMPLETE**

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

### Phase 2: Waiter Intelligence System
- [x] `WaiterInsights` model for storing LLM-generated analysis
- [x] `MetricsAggregator` service - computes 30-day rolling metrics
- [x] `TierCalculator` service - Z-score normalization + PRD formula
- [x] `LLMScorer` service - robust LLM response parsing with fallbacks
- [x] `TierRecalculationJob` - weekly job orchestrator (cron-compatible)
- [x] `DashboardService` - aggregates waiter dashboard data
- [x] `SeedService` - cold start data seeding
- [x] Dashboard API endpoints:
  - `GET /waiters/{id}/stats` - this month stats
  - `GET /waiters/{id}/trends` - 6-month trend data
  - `GET /waiters/{id}/insights` - LLM strengths/areas/suggestions
  - `GET /waiters/{id}/shifts` - recent shifts
  - `GET /waiters/{id}/dashboard` - unified endpoint
  - `POST /restaurants/{id}/recalculate-tiers` - trigger tier job
- [x] Cron entry point: `python -m app.jobs.tier_recalculation`
- [x] LLM config in settings (OpenRouter, bytedance-seed/seed-1.6)
- [x] 45 new tests (165 total passing)

### Phase 3: Scheduling System (Agent 1)
**Sub-task 1: Data Layer** - COMPLETE
- [x] Extended Waiter model with `role` field (server, bartender, host, busser, runner)
- [x] Added role-based scheduling properties (`requires_performance_tracking`, `is_availability_only`)
- [x] 7 new scheduling models in `app/models/scheduling.py`:
  - StaffAvailability (recurring weekly patterns like 7shifts)
  - StaffPreference (role, shift type, section preferences, max hours)
  - Schedule (weekly container with versioning)
  - ScheduleItem (individual shift assignments with scores)
  - ScheduleRun (engine run metadata)
  - ScheduleReasoning (per-item explanations)
  - StaffingRequirements (coverage config per time slot)
- [x] Full Pydantic schemas for all scheduling entities
- [x] 18 API endpoints in `app/api/scheduling.py`:
  - Staff availability CRUD + bulk create
  - Staff preferences upsert
  - Schedules CRUD + publish + audit
  - Schedule items CRUD
  - Staffing requirements CRUD
  - Engine run trigger + status

**Sub-task 2: Scheduling Engine** - COMPLETE
- [x] `DemandForecaster` service - weighted historical averages + trend prediction
- [x] `ConstraintValidator` service - hard/soft constraint validation
- [x] `FairnessCalculator` service - Gini coefficient, hours balance, prime shift equity
- [x] `SchedulingEngine` service - score-and-rank algorithm orchestrator
- [x] `ScheduleReasoningGenerator` service - rule-based + optional LLM explanations
- [x] Engine integrated with run endpoint (`POST /api/v1/restaurants/{id}/schedules/run`)
- [x] 46 new tests (211 total passing)
- [x] Frontend call guide updated (`Frontend_Call_Guide_Scheduling_Analytics.md`)

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

### Waiter Intelligence Services
- `app/models/insights.py` - WaiterInsights model
- `app/schemas/insights.py` - Dashboard schemas
- `app/services/metrics_aggregator.py` - Metrics computation
- `app/services/tier_calculator.py` - Tier scoring logic
- `app/services/llm_scorer.py` - LLM integration with robust parsing
- `app/services/tier_job.py` - Weekly job orchestrator
- `app/services/dashboard_service.py` - Dashboard data aggregation
- `app/services/seed_service.py` - Cold start data seeding
- `app/api/waiter_dashboard.py` - Dashboard endpoints
- `app/jobs/__init__.py` - Jobs module
- `app/jobs/tier_recalculation.py` - Cron entry point

### Scheduling System
- `app/models/scheduling.py` - 7 scheduling models
- `app/schemas/scheduling.py` - Full Pydantic schemas
- `app/api/scheduling.py` - 18 CRUD endpoints
- `app/services/demand_forecaster.py` - Weighted avg + trend prediction
- `app/services/scheduling_constraints.py` - Hard/soft constraint validation
- `app/services/fairness_calculator.py` - Gini coefficient + hours balance
- `app/services/scheduling_engine.py` - Score-and-rank orchestrator
- `app/services/schedule_reasoning.py` - Explanation generation

### Tests
- `tests/__init__.py`
- `tests/conftest.py` - Fixtures with realistic restaurant data
- `tests/test_models.py` - SQLAlchemy model tests
- `tests/test_schemas.py` - Pydantic validation tests
- `tests/test_tier_calculator.py` - Tier calculation tests
- `tests/test_llm_scorer.py` - LLM parsing tests
- `tests/test_scheduling.py` - Scheduling data layer tests (28 tests)
- `tests/test_scheduling_engine.py` - Engine service tests (18 tests)
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

- All 211 tests passing
- ML services in `app/ml/` - enable with `ML_ENABLED=true`
- **POC code in `_legacy_poc/` is reference only - do not modify**
- Use JSON instead of JSONB for SQLite test compatibility
- Reference PRD.md Section 4.2 for routing algorithm details
- Reference `Frontend_Call_Guide_Scheduling_Analytics.md` for scheduling API usage
- Scheduling engine uses score-and-rank algorithm with:
  - Weighted historical demand forecasting
  - Hard/soft constraint validation
  - Fairness scoring (Gini coefficient)
  - Role-based scheduling (servers/bartenders get performance tracking, hosts/bussers/runners are availability-only)

## Phase Overview

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | PostgreSQL Schema + Core Models | **COMPLETE** |
| 2 | Routing API + Waiter Intelligence | **COMPLETE** |
| 3 | State + Waitlist Endpoints | Done |
| 4 | Analytics/Dashboard Endpoints | **COMPLETE** |
| 5 | Scheduling System (Agent 1) | **COMPLETE** |
| 6 | Webhooks (ML/POS) | Pending |
| 7 | WebSocket Layer | Pending |
