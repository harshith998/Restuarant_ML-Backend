# Restaurant Intelligence Platform - API Documentation

> Complete reference for all REST API and ML endpoints.

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Base URL & Versioning](#base-url--versioning)
4. [Health Endpoints](#health-endpoints)
5. [Restaurant Endpoints](#restaurant-endpoints)
6. [Table Endpoints](#table-endpoints)
7. [Waiter Endpoints](#waiter-endpoints)
8. [Shift Endpoints](#shift-endpoints)
9. [Waitlist Endpoints](#waitlist-endpoints)
10. [Visit Endpoints](#visit-endpoints)
11. [Routing Endpoints](#routing-endpoints)
12. [ML Endpoints](#ml-endpoints)
13. [Crop/Camera Endpoints](#cropcamera-endpoints)
14. [Database Schema Reference](#database-schema-reference)
15. [Error Handling](#error-handling)

---

## Overview

### Purpose
The Restaurant Intelligence Platform is a PostgreSQL-backed API that provides:
- **Real-time table state detection** via ML image classification
- **Intelligent party routing** with waiter load balancing
- **Full restaurant operations management** (waitlist, visits, shifts)

### Core Workflow
```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Camera    │────▶│  ML Predict  │────▶│   Postgres  │
│   Feed      │     │  /ml/predict │     │ Table State │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
┌─────────────┐     ┌──────────────┐            │
│   Host      │────▶│   Routing    │◀───────────┘
│   Request   │     │  /recommend  │
└─────────────┘     └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │   Seat Party │
                    │    /seat     │
                    └──────────────┘
```

### Technology Stack
- **FastAPI** - Async REST framework
- **SQLAlchemy** - Async ORM with PostgreSQL
- **Pydantic** - Request/response validation
- **PyTorch/DINOv3** - Table state classification
- **Alembic** - Database migrations

---

## Authentication

> **Current Status**: No authentication implemented.
>
> **Future**: JWT tokens via `Authorization: Bearer <token>` header.

---

## Base URL & Versioning

| Environment | Base URL |
|-------------|----------|
| Local | `http://localhost:8000` |
| Railway | `https://your-app.railway.app` |

**API Version Prefix**: `/api/v1`

All REST endpoints (except ML and health) use the `/api/v1` prefix.

---

## Health Endpoints

### `GET /healthz`
Application-level health check.

**Response**:
```json
{
  "status": "ok",
  "service": "restaurant-intelligence-platform"
}
```

**Purpose**: Used by Railway for deployment health checks. Returns 200 if the FastAPI app is running.

**Postgres Connection**: None - this is a simple liveness check.

---

### `GET /ml/healthz`
ML service health check.

**Response**:
```json
{
  "status": "ok",
  "model_loaded": true
}
```

**Purpose**: Verifies the DINOv3 classifier model is loaded and ready for inference.

**Postgres Connection**: None.

---

### `GET /crops/healthz`
Crop/camera service health check.

**Response**:
```json
{
  "status": "ok"
}
```

---

## Restaurant Endpoints

### Design Philosophy
Restaurants are the **top-level organizational unit**. All other entities (tables, waiters, sections, shifts) belong to a restaurant. The restaurant's `config` JSON stores operational settings like routing mode.

---

### `GET /api/v1/restaurants`
List all restaurants.

**Query Parameters**: None

**Response** (`List[RestaurantRead]`):
```json
[
  {
    "id": "uuid",
    "name": "The Golden Fork",
    "timezone": "America/New_York",
    "config": {
      "routing": {
        "mode": "section",
        "max_tables_per_waiter": 5
      }
    },
    "created_at": "2024-01-15T10:00:00Z",
    "updated_at": "2024-01-15T10:00:00Z"
  }
]
```

**Postgres**: `SELECT * FROM restaurants ORDER BY name`

---

### `GET /api/v1/restaurants/{restaurant_id}`
Get a single restaurant by ID.

**Path Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| restaurant_id | UUID | Yes | Restaurant primary key |

**Response** (`RestaurantRead`): Same as above, single object.

**Errors**:
- `404`: Restaurant not found

---

### `POST /api/v1/restaurants`
Create a new restaurant.

**Request Body** (`RestaurantCreate`):
```json
{
  "name": "The Golden Fork",
  "timezone": "America/New_York",
  "config": {}
}
```

| Field | Type | Required | Default | Validation |
|-------|------|----------|---------|------------|
| name | string | Yes | - | 1-255 chars |
| timezone | string | No | "America/New_York" | Max 50 chars |
| config | object | No | {} | Any JSON |

**Response**: Created `RestaurantRead` with generated UUID.

**Postgres**: `INSERT INTO restaurants (name, timezone, config) VALUES (...)`

---

### `PATCH /api/v1/restaurants/{restaurant_id}`
Update a restaurant.

**Request Body** (`RestaurantUpdate`):
```json
{
  "name": "New Name",
  "config": {"routing": {"mode": "rotation"}}
}
```

All fields optional. Only provided fields are updated.

**Postgres**: `UPDATE restaurants SET name = ?, config = ? WHERE id = ?`

---

### `GET /api/v1/restaurants/{restaurant_id}/config`
Get restaurant configuration with defaults.

**Response**:
```json
{
  "restaurant_id": "uuid",
  "name": "The Golden Fork",
  "timezone": "America/New_York",
  "routing": {
    "mode": "section",
    "max_tables_per_waiter": 5
  },
  "raw_config": {}
}
```

**Purpose**: Returns config with sensible defaults merged in, useful for frontend without null-checking.

---

## Table Endpoints

### Design Philosophy
Tables represent physical seating locations. Their **state** (`clean`, `occupied`, `dirty`) is the core data the system tracks. States can be updated by:
1. **ML predictions** - Camera images analyzed automatically
2. **Host override** - Manual correction via API
3. **System** - Automatic transitions (e.g., `occupied` when seated)

Every state change creates a `TableStateLog` entry for audit/debugging.

---

### Table States

| State | Description | Typical Duration |
|-------|-------------|------------------|
| `clean` | Ready for seating | Until seated |
| `occupied` | Party currently seated | 45-90 minutes |
| `dirty` | Party left, needs bussing | 5-10 minutes |
| `reserved` | Held for reservation | Until party arrives |
| `unavailable` | Out of service | Variable |

---

### Table Types & Locations

**Types**:
- `booth` - Fixed bench seating
- `table` - Standard table

**Locations**:
- `inside` - Main dining room
- `outside` - Outdoor seating

---

### `GET /api/v1/restaurants/{restaurant_id}/tables`
List all tables for a restaurant.

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| state | string | null | Filter by state (clean, occupied, dirty) |
| section_id | UUID | null | Filter by section |
| include_inactive | bool | false | Include inactive tables |

**Response** (`List[TableRead]`):
```json
[
  {
    "id": "uuid",
    "restaurant_id": "uuid",
    "section_id": "uuid",
    "table_number": "T1",
    "capacity": 4,
    "table_type": "booth",
    "location": "inside",
    "state": "clean",
    "state_confidence": 0.95,
    "state_updated_at": "2024-01-15T10:30:00Z",
    "current_visit_id": null,
    "is_active": true,
    "created_at": "2024-01-15T10:00:00Z",
    "updated_at": "2024-01-15T10:30:00Z"
  }
]
```

**Postgres**:
```sql
SELECT * FROM tables
WHERE restaurant_id = ?
  AND (state = ? OR ? IS NULL)
  AND (section_id = ? OR ? IS NULL)
ORDER BY table_number
```

---

### `GET /api/v1/restaurants/{restaurant_id}/tables/section-view`
Get section view with tables grouped by section.

**Response**:
```json
[
  {
    "id": "uuid",
    "table_number": "T1",
    "capacity": 4,
    "table_type": "booth",
    "location": "inside",
    "state": "occupied",
    "section_name": "Main Floor",
    "waiter_name": "Alice",
    "party_size": 3,
    "seated_duration_minutes": 45
  }
]
```

**Purpose**: Optimized for UI section view. Includes section names and active visit info without separate lookups.

---

### `GET /api/v1/tables/{table_id}`
Get a single table by ID.

**Response**: `TableRead` object.

---

### `POST /api/v1/restaurants/{restaurant_id}/tables`
Create a new table.

**Request Body** (`TableCreate`):
```json
{
  "table_number": "T15",
  "capacity": 4,
  "table_type": "booth",
  "location": "inside",
  "section_id": "uuid-optional"
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| table_number | string | Yes | 1-20 chars, unique per restaurant |
| capacity | int | Yes | 1-20 |
| table_type | enum | Yes | booth, table |
| location | enum | No | inside, outside |
| section_id | UUID | No | Must exist if provided |

**Postgres**: `INSERT INTO tables (...) VALUES (...)`

---

### `PATCH /api/v1/tables/{table_id}`
Update table properties (NOT state).

**Request Body** (`TableUpdate`):
```json
{
  "capacity": 6,
  "section_id": "new-section-uuid"
}
```

**Purpose**: Use this for property changes. For state changes, use `PATCH /tables/{id}/state`.

---

### `PATCH /api/v1/tables/{table_id}/state`
Update table state with audit logging.

**Request Body** (`TableStateUpdate`):
```json
{
  "state": "clean",
  "source": "host",
  "confidence": 1.0
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| state | enum | Yes | clean, occupied, dirty, reserved, unavailable |
| source | string | Yes | ml, host, system |
| confidence | float | No | 0.0 - 1.0 |

**Postgres Operations**:
1. `SELECT * FROM tables WHERE id = ?` - Get current state
2. `INSERT INTO table_state_logs (table_id, previous_state, new_state, confidence, source)` - Create audit log
3. `UPDATE tables SET state = ?, state_confidence = ?, state_updated_at = NOW()` - Update table

**Response**: Updated `TableRead`

---

### `GET /api/v1/tables/{table_id}/history`
Get state change history for debugging.

**Query Parameters**:
| Parameter | Type | Default | Max |
|-----------|------|---------|-----|
| limit | int | 50 | 200 |

**Response**:
```json
[
  {
    "id": "uuid",
    "previous_state": "occupied",
    "new_state": "dirty",
    "confidence": 0.98,
    "source": "ml",
    "created_at": "2024-01-15T11:30:00Z"
  }
]
```

**Purpose**: Debug ML accuracy, track manual overrides, understand state transitions.

**Postgres**: `SELECT * FROM table_state_logs WHERE table_id = ? ORDER BY created_at DESC LIMIT ?`

---

### `GET /api/v1/restaurants/{restaurant_id}/tables/stats`
Get table state statistics.

**Response**:
```json
{
  "total": 20,
  "by_state": {
    "clean": 8,
    "occupied": 10,
    "dirty": 2
  },
  "available": 8,
  "occupied": 10,
  "needs_cleaning": 2
}
```

**Purpose**: Dashboard metrics, capacity planning.

---

## Waiter Endpoints

### Design Philosophy
Waiters are scored using a **composite score** that considers:
- Tip percentage performance
- Customer feedback (future)
- Tables served efficiency

Waiters are tiered (`strong`, `standard`, `developing`) based on historical performance. The routing algorithm uses these tiers to balance workload fairly.

---

### Waiter Tiers

| Tier | Description | Score Range |
|------|-------------|-------------|
| `strong` | Top performers | 80-100 |
| `standard` | Solid performers | 50-79 |
| `developing` | New or improving | 0-49 |

---

### `GET /api/v1/restaurants/{restaurant_id}/waiters`
List all waiters for a restaurant.

**Query Parameters**:
| Parameter | Type | Default |
|-----------|------|---------|
| include_inactive | bool | false |

**Response** (`List[WaiterRead]`):
```json
[
  {
    "id": "uuid",
    "restaurant_id": "uuid",
    "name": "Alice Johnson",
    "email": "alice@example.com",
    "phone": "555-1234",
    "tier": "strong",
    "composite_score": 85.5,
    "tier_updated_at": "2024-01-01T00:00:00Z",
    "total_shifts": 150,
    "total_covers": 2400,
    "total_tips": 18500.00,
    "is_active": true,
    "created_at": "2023-06-01T00:00:00Z",
    "updated_at": "2024-01-15T10:00:00Z"
  }
]
```

---

### `GET /api/v1/restaurants/{restaurant_id}/waiters/active`
Get waiters currently on shift with real-time stats.

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| section_id | UUID | Filter by section |

**Response**:
```json
[
  {
    "id": "uuid",
    "name": "Alice Johnson",
    "tier": "strong",
    "composite_score": 85.5,
    "current_tables": 3,
    "current_tips": 45.00,
    "current_covers": 8,
    "section_id": "uuid",
    "status": "available"
  }
]
```

**Purpose**: Real-time view for routing decisions and manager dashboard.

**Postgres**: Joins `waiters` with active `shifts` and counts active `visits`.

---

### `GET /api/v1/waiters/{waiter_id}/stats`
Get aggregated stats for a waiter for a period.

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| period | string | month | month, week, or day |

**Response**:
```json
{
  "covers": 120,
  "tips": 480.5,
  "avg_per_cover": 38.5,
  "efficiency_pct": 92.3,
  "tables_served": 45,
  "total_sales": 4620.0
}
```

---

### `GET /api/v1/waiters/{waiter_id}/dashboard`
Get complete dashboard data for a waiter (profile, stats, trends, insights).

**Response (shape)**:
```json
{
  "profile": {
    "id": "uuid",
    "name": "Alice Johnson",
    "email": "alice@example.com",
    "phone": null,
    "tier": "strong",
    "tenure_years": 1.4,
    "total_shifts": 120,
    "total_covers": 1800,
    "total_tips": 14200.0,
    "is_active": true,
    "created_at": "2026-01-01T12:00:00Z"
  },
  "stats": {
    "covers": 120,
    "tips": 480.5,
    "avg_per_cover": 38.5,
    "efficiency_pct": 92.3,
    "tables_served": 45,
    "total_sales": 4620.0
  },
  "trends": [],
  "insights": null,
  "recent_shifts": []
}
```

---

### `GET /api/v1/waiters/{waiter_id}`
Get a single waiter by ID.

---

### `POST /api/v1/restaurants/{restaurant_id}/waiters`
Create a new waiter.

**Request Body** (`WaiterCreate`):
```json
{
  "name": "New Waiter",
  "email": "new@example.com",
  "phone": "555-0000"
}
```

| Field | Type | Required |
|-------|------|----------|
| name | string | Yes (1-100 chars) |
| email | string | No (valid email) |
| phone | string | No (max 20 chars) |

**Defaults**: `tier = "developing"`, `composite_score = 0.0`

---

### `PATCH /api/v1/waiters/{waiter_id}`
Update a waiter.

---

### `GET /api/v1/restaurants/{restaurant_id}/waiters/leaderboard`
Get waiter leaderboard by composite score.

**Query Parameters**:
| Parameter | Type | Default | Max |
|-----------|------|---------|-----|
| limit | int | 10 | 50 |

**Response**:
```json
[
  {
    "rank": 1,
    "id": "uuid",
    "name": "Alice Johnson",
    "tier": "strong",
    "composite_score": 85.5,
    "total_shifts": 150,
    "total_covers": 2400,
    "total_tips": 18500.00
  }
]
```

**Purpose**: Gamification, performance tracking.

---

## Shift Endpoints

### Design Philosophy
Shifts track a waiter's clock-in to clock-out period. They accumulate:
- Tables served
- Covers (people served)
- Tips earned
- Total sales

The routing algorithm only considers waiters with **active shifts**.

---

### Shift Statuses

| Status | Description |
|--------|-------------|
| `active` | Currently working, can receive tables |
| `on_break` | Temporarily unavailable |
| `ended` | Shift complete |

---

### `GET /api/v1/restaurants/{restaurant_id}/shifts`
List shifts with optional filters.

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| status | string | Filter by status |
| waiter_id | UUID | Filter by waiter |

**Response** (`List[ShiftRead]`):
```json
[
  {
    "id": "uuid",
    "restaurant_id": "uuid",
    "waiter_id": "uuid",
    "section_id": "uuid",
    "clock_in": "2024-01-15T09:00:00Z",
    "clock_out": null,
    "status": "active",
    "tables_served": 5,
    "total_covers": 18,
    "total_tips": 125.00,
    "total_sales": 850.00,
    "created_at": "2024-01-15T09:00:00Z",
    "updated_at": "2024-01-15T12:00:00Z"
  }
]
```

---

### `GET /api/v1/restaurants/{restaurant_id}/shifts/active`
Get only active/on-break shifts.

**Purpose**: Quick lookup for routing - only these waiters can receive new tables.

---

### `GET /api/v1/shifts/{shift_id}`
Get a single shift.

---

### `POST /api/v1/shifts`
Clock in a waiter (create shift).

**Request Body** (`ShiftCreate`):
```json
{
  "restaurant_id": "uuid",
  "waiter_id": "uuid",
  "section_id": "uuid-optional",
  "clock_in": "2024-01-15T09:00:00Z"
}
```

| Field | Type | Required | Default |
|-------|------|----------|---------|
| restaurant_id | UUID | Yes | - |
| waiter_id | UUID | Yes | - |
| section_id | UUID | No | null |
| clock_in | datetime | No | NOW() |

**Validations**:
- Waiter must exist
- Waiter cannot have an existing active/on_break shift

**Error**: `400` if waiter already clocked in

---

### `PATCH /api/v1/shifts/{shift_id}`
Update shift (generic update).

**Request Body** (`ShiftUpdate`):
```json
{
  "status": "ended",
  "clock_out": "2024-01-15T17:00:00Z"
}
```

**Auto-behavior**: If `status` set to `ended` without `clock_out`, sets `clock_out = NOW()`.

---

### `POST /api/v1/shifts/{shift_id}/break`
Take a break.

**Precondition**: Shift status must be `active`

**Effect**: Sets `status = "on_break"`

---

### `POST /api/v1/shifts/{shift_id}/resume`
Resume from break.

**Precondition**: Shift status must be `on_break`

**Effect**: Sets `status = "active"`

---

### `POST /api/v1/shifts/{shift_id}/end`
Clock out (end shift).

**Effect**:
- Sets `status = "ended"`
- Sets `clock_out = NOW()`

---

## Waitlist Endpoints

### Design Philosophy
The waitlist manages parties waiting to be seated. It tracks:
- Wait time (quoted vs actual)
- Party preferences (table type, location)
- Outcome (seated, walked away)

Waitlist entries are linked to visits when seated, enabling wait-to-seat time analysis.

---

### Waitlist Statuses

| Status | Description |
|--------|-------------|
| `waiting` | In queue, not yet seated |
| `seated` | Party has been seated |
| `walked_away` | Left without being seated |

---

### `GET /api/v1/restaurants/{restaurant_id}/waitlist`
List waitlist entries.

**Query Parameters**:
| Parameter | Type | Default |
|-----------|------|---------|
| status | string | "waiting" |

**Response** (`List[WaitlistRead]`):
```json
[
  {
    "id": "uuid",
    "restaurant_id": "uuid",
    "party_name": "Smith",
    "party_size": 4,
    "table_preference": "booth",
    "location_preference": "inside",
    "notes": "Birthday celebration",
    "checked_in_at": "2024-01-15T18:00:00Z",
    "quoted_wait_minutes": 20,
    "status": "waiting",
    "seated_at": null,
    "walked_away_at": null,
    "visit_id": null,
    "created_at": "2024-01-15T18:00:00Z"
  }
]
```

---

### `GET /api/v1/restaurants/{restaurant_id}/waitlist/queue`
Get queue with wait time calculations.

**Response**:
```json
{
  "total_waiting": 5,
  "queue": [
    {
      "position": 1,
      "id": "uuid",
      "party_name": "Smith",
      "party_size": 4,
      "table_preference": "booth",
      "location_preference": "inside",
      "checked_in_at": "2024-01-15T18:00:00Z",
      "wait_so_far_minutes": 15,
      "quoted_wait_minutes": 20
    }
  ]
}
```

**Purpose**: Customer-facing wait display, host queue management.

---

### `GET /api/v1/waitlist/{entry_id}`
Get a single waitlist entry.

---

### `POST /api/v1/restaurants/{restaurant_id}/waitlist`
Add a party to the waitlist.

**Request Body** (`WaitlistCreate`):
```json
{
  "party_name": "Smith",
  "party_size": 4,
  "table_preference": "booth",
  "location_preference": "inside",
  "notes": "Birthday celebration",
  "quoted_wait_minutes": 20
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| party_name | string | No | Max 100 chars |
| party_size | int | Yes | 1-20 |
| table_preference | enum | No | booth, table, none |
| location_preference | enum | No | inside, outside, none |
| notes | string | No | - |
| quoted_wait_minutes | int | No | >= 0 |

**Defaults**: `status = "waiting"`, `checked_in_at = NOW()`

---

### `PATCH /api/v1/waitlist/{entry_id}`
Update a waitlist entry.

---

### `POST /api/v1/waitlist/{entry_id}/walk-away`
Mark party as walked away.

**Precondition**: Status must be `waiting`

**Effect**:
- Sets `status = "walked_away"`
- Sets `walked_away_at = NOW()`

---

### `DELETE /api/v1/waitlist/{entry_id}`
Delete a waitlist entry.

**Precondition**: Status must be `waiting`

---

## Visit Endpoints

### Design Philosophy
Visits represent a party's time at a table from seating to departure. They track:
- Timing (seated, served, payment, cleared)
- Financial (subtotal, tax, total, tip)
- Attribution (waiter, shift, waitlist origin)

Visits drive waiter performance metrics and enable duration analysis.

---

### Visit Lifecycle

```
┌─────────┐     ┌──────────┐     ┌─────────┐     ┌─────────┐
│ Seated  │────▶│  Served  │────▶│ Payment │────▶│ Cleared │
│         │     │          │     │         │     │         │
└─────────┘     └──────────┘     └─────────┘     └─────────┘
 seated_at      first_served_at   payment_at     cleared_at
```

---

### `GET /api/v1/restaurants/{restaurant_id}/visits`
List visits.

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| active_only | bool | true | Exclude cleared visits |
| table_id | UUID | null | Filter by table |
| waiter_id | UUID | null | Filter by waiter |

**Response** (`List[VisitRead]`):
```json
[
  {
    "id": "uuid",
    "restaurant_id": "uuid",
    "table_id": "uuid",
    "waiter_id": "uuid",
    "shift_id": "uuid",
    "waitlist_id": "uuid",
    "party_size": 4,
    "actual_covers": 4,
    "seated_at": "2024-01-15T18:30:00Z",
    "first_served_at": "2024-01-15T18:35:00Z",
    "payment_at": null,
    "cleared_at": null,
    "duration_minutes": null,
    "subtotal": null,
    "tax": null,
    "total": null,
    "tip": null,
    "tip_percentage": null,
    "pos_transaction_id": null,
    "original_waiter_id": null,
    "transferred_at": null,
    "created_at": "2024-01-15T18:30:00Z",
    "updated_at": "2024-01-15T18:35:00Z"
  }
]
```

---

### `GET /api/v1/visits/{visit_id}`
Get a single visit.

---

### `POST /api/v1/visits`
Create a visit manually.

> **Note**: Prefer using `POST /routing/seat` which handles table state updates automatically.

**Request Body** (`VisitCreate`):
```json
{
  "restaurant_id": "uuid",
  "table_id": "uuid",
  "waiter_id": "uuid",
  "shift_id": "uuid",
  "waitlist_id": "uuid-optional",
  "party_size": 4,
  "seated_at": "2024-01-15T18:30:00Z"
}
```

**Side Effects**:
- Updates table state to `occupied`
- Sets `current_visit_id` on table

---

### `PATCH /api/v1/visits/{visit_id}`
Update visit details.

**Request Body** (`VisitUpdate`):
```json
{
  "actual_covers": 4,
  "first_served_at": "2024-01-15T18:35:00Z",
  "subtotal": 120.00,
  "tax": 10.80,
  "total": 130.80,
  "tip": 26.00
}
```

**Auto-calculations**:
- If `tip` and `total` provided: calculates `tip_percentage = (tip / total) * 100`
- If `cleared_at` provided: calculates `duration_minutes`

---

### `POST /api/v1/visits/{visit_id}/payment`
Record payment for a visit.

**Query Parameters**:
| Parameter | Type | Required |
|-----------|------|----------|
| subtotal | float | Yes |
| tax | float | Yes |
| total | float | Yes |
| tip | float | Yes |
| pos_transaction_id | string | No |

**Side Effects**:
- Sets `payment_at = NOW()`
- Calculates `tip_percentage`

---

### `POST /api/v1/visits/{visit_id}/clear`
Mark visit as cleared (party left).

**Side Effects**:
- Sets `cleared_at = NOW()`
- Calculates `duration_minutes`
- Marks table as `dirty`

---

### `POST /api/v1/visits/{visit_id}/transfer`
Transfer visit to another waiter.

**Query Parameters**:
| Parameter | Type | Required |
|-----------|------|----------|
| new_waiter_id | UUID | Yes |

**Side Effects**:
- Stores `original_waiter_id` (first transfer only)
- Sets `transferred_at = NOW()`

---

## Routing Endpoints

### Design Philosophy
The routing system provides **intelligent table and waiter assignment**. It considers:
- Party preferences (table type, location)
- Table availability and capacity
- Waiter workload and tier
- Restaurant routing mode (section vs rotation)

---

### Routing Modes

| Mode | Description |
|------|-------------|
| `section` | Tables assigned to sections, waiters serve their section |
| `rotation` | Round-robin waiter assignment regardless of section |

---

### `POST /api/v1/restaurants/{restaurant_id}/routing/recommend`
Get a seating recommendation.

**Request Body** (`RouteRequest`):
```json
{
  "waitlist_id": "uuid-optional",
  "party_size": 4,
  "table_preference": "booth",
  "location_preference": "inside"
}
```

| Field | Type | Description |
|-------|------|-------------|
| waitlist_id | UUID | If seating from waitlist, preferences are pulled from entry |
| party_size | int | Required if no waitlist_id |
| table_preference | enum | booth, table, none |
| location_preference | enum | inside, outside, none |

**Response** (`RouteResponse`):
```json
{
  "success": true,
  "table_id": "uuid",
  "table_number": "T5",
  "table_type": "booth",
  "table_location": "inside",
  "table_capacity": 4,
  "waiter_id": "uuid",
  "waiter_name": "Alice Johnson",
  "section_id": "uuid",
  "section_name": "Main Floor",
  "match_details": {
    "type_matched": true,
    "location_matched": true,
    "capacity_fit": 4
  },
  "message": null
}
```

**Algorithm**:
1. Find clean tables matching capacity (`party_size <= capacity`)
2. Score tables by preference match and capacity efficiency
3. Select best table
4. Find available waiter (by section in section mode, by load in rotation mode)
5. Return recommendation

**Does NOT seat the party** - use `POST /routing/seat` to execute.

---

### `POST /api/v1/restaurants/{restaurant_id}/routing/seat`
Execute seating after route decision.

**Query Parameters**:
| Parameter | Type | Required |
|-----------|------|----------|
| table_id | UUID | Yes |
| waiter_id | UUID | Yes |
| party_size | int | Yes |
| waitlist_id | UUID | No |

**Side Effects**:
1. Creates Visit record
2. Updates table state to `occupied`
3. Updates table `current_visit_id`
4. If `waitlist_id` provided, marks waitlist entry as `seated`
5. Increments shift stats (tables_served)

**Response**: Created `VisitRead`

---

### `POST /api/v1/restaurants/{restaurant_id}/routing/mode`
Switch routing mode.

**Query Parameters**:
| Parameter | Type | Required | Values |
|-----------|------|----------|--------|
| mode | string | Yes | section, rotation |

**Response**:
```json
{
  "status": "ok",
  "mode": "rotation"
}
```

**Postgres**: Updates `restaurants.config.routing.mode`

---

## ML Endpoints

### Design Philosophy
The ML system provides **automated table state detection** using a DINOv3 classifier trained on table images. It can:
1. Run predictions ephemerally (just return result)
2. Auto-update Postgres table state (when `table_id` provided)

---

### `POST /ml/predict`
Classify table state from image.

**Request** (multipart/form-data):
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| file | file | Yes | Image file (jpg, png, etc.) |
| table_id | string | No | UUID of table to auto-update |

**Response** (without table_id):
```json
{
  "label": "clean",
  "confidence": 0.95,
  "probabilities": {
    "clean": 0.95,
    "occupied": 0.03,
    "dirty": 0.02
  }
}
```

**Response** (with table_id):
```json
{
  "label": "dirty",
  "confidence": 0.98,
  "probabilities": {
    "clean": 0.01,
    "occupied": 0.01,
    "dirty": 0.98
  },
  "table_updated": true,
  "table_id": "uuid"
}
```

**Classes**:
| Class | Description |
|-------|-------------|
| `clean` | Empty, clean table ready for seating |
| `occupied` | Party currently seated |
| `dirty` | Party left, dishes/debris visible |

**Postgres Operations** (when table_id provided):
1. Parse and validate UUID
2. Call `update_table_state(table_id, label, confidence, source="ml")`
3. Creates `TableStateLog` entry
4. Updates `tables.state`, `state_confidence`, `state_updated_at`

**Error Handling**:
- If table_id not found: prediction still returned with `table_updated: false` and `table_update_error`
- If DB error: prediction still returned with error details

---

### Example: Testing with cURL

```bash
# Ephemeral prediction (no DB update)
curl -X POST http://localhost:8000/ml/predict \
  -F "file=@table_image.jpg"

# With DB update
curl -X POST http://localhost:8000/ml/predict \
  -F "file=@table_image.jpg" \
  -F "table_id=550e8400-e29b-41d4-a716-446655440000"
```

---

## Crop/Camera Endpoints

### Design Philosophy
The crop system manages camera feeds that provide images to the ML classifier. Each camera:
- Has a video source (RTSP URL, file path, etc.)
- Has crop JSON defining table bounding boxes
- Periodically captures frames and dispatches crops to `/ml/predict`

---

### `GET /crops/cameras`
List registered cameras.

**Response**:
```json
{
  "cameras": [
    {
      "camera_id": "cam-1",
      "video_source": "rtsp://192.168.1.100/stream",
      "last_capture_ts": "2024-01-15T12:00:00Z",
      "last_frame_index": 1523,
      "has_crop_json": true
    }
  ]
}
```

---

### `POST /crops/cameras/register`
Register a new camera.

**Request Body**:
```json
{
  "camera_id": "cam-1",
  "video_source": "rtsp://192.168.1.100/stream",
  "crop_json": {
    "tables": [
      {
        "table_id": "uuid",
        "table_number": "T1",
        "bbox": [100, 100, 300, 300]
      }
    ]
  }
}
```

---

### `POST /crops/cameras/{camera_id}/crop-json`
Update crop JSON for a camera.

**Request Body**:
```json
{
  "crop_json": {
    "tables": [
      {
        "table_id": "uuid",
        "table_number": "T1",
        "bbox": [100, 100, 300, 300]
      }
    ]
  }
}
```

**Purpose**: Allows updating table bounding boxes without re-registering the camera.

---

### `POST /crops/cameras/{camera_id}/refresh`
Request crop JSON refresh.

**Purpose**: Triggers a re-fetch of crop definitions from configuration source.

---

## Database Schema Reference

### Core Tables

```
┌─────────────────┐
│   restaurants   │
├─────────────────┤
│ id (PK)         │
│ name            │
│ timezone        │
│ config (JSONB)  │
│ created_at      │
│ updated_at      │
└────────┬────────┘
         │
         │ 1:N
         ▼
┌─────────────────┐     ┌─────────────────┐
│    sections     │     │     waiters     │
├─────────────────┤     ├─────────────────┤
│ id (PK)         │     │ id (PK)         │
│ restaurant_id   │     │ restaurant_id   │
│ name            │     │ name            │
│ priority        │     │ tier            │
└────────┬────────┘     │ composite_score │
         │              └────────┬────────┘
         │ 1:N                   │ 1:N
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│     tables      │     │     shifts      │
├─────────────────┤     ├─────────────────┤
│ id (PK)         │     │ id (PK)         │
│ restaurant_id   │     │ restaurant_id   │
│ section_id (FK) │     │ waiter_id (FK)  │
│ table_number    │     │ section_id (FK) │
│ capacity        │     │ clock_in        │
│ state           │     │ clock_out       │
│ state_confidence│     │ status          │
│ current_visit_id│     │ tables_served   │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     │
                     ▼
            ┌─────────────────┐
            │     visits      │
            ├─────────────────┤
            │ id (PK)         │
            │ restaurant_id   │
            │ table_id (FK)   │
            │ waiter_id (FK)  │
            │ shift_id (FK)   │
            │ waitlist_id (FK)│
            │ party_size      │
            │ seated_at       │
            │ cleared_at      │
            │ tip             │
            └─────────────────┘
```

### Supporting Tables

| Table | Purpose |
|-------|---------|
| `waitlist_entries` | Party queue management |
| `table_state_logs` | State change audit trail |
| `menu_items` | Restaurant menu (future) |
| `order_items` | Individual orders (future) |
| `waiter_metrics` | Historical performance |
| `restaurant_metrics` | Aggregated stats |
| `camera_sources` | Registered cameras |
| `camera_crop_states` | Crop definitions |
| `crop_dispatch_logs` | ML dispatch history |

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | Success | GET, PATCH succeeded |
| 201 | Created | POST created resource |
| 400 | Bad Request | Validation failed, invalid state transition |
| 404 | Not Found | Resource doesn't exist |
| 415 | Unsupported Media Type | Non-image file to /ml/predict |
| 503 | Service Unavailable | ML model not loaded |

### Error Response Format

```json
{
  "detail": "Restaurant not found"
}
```

### Common Errors

| Endpoint | Error | Cause |
|----------|-------|-------|
| POST /shifts | "Waiter already has active shift" | Cannot double clock-in |
| POST /shifts/{id}/break | "Cannot take break - shift is ended" | Invalid state transition |
| PATCH /tables/{id}/state | "Table not found" | Invalid UUID |
| POST /ml/predict | "Model not loaded" | ML_ENABLED=false or startup failed |
| POST /routing/seat | "No available tables" | All tables occupied |

---

## Appendix: Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| DATABASE_URL | Yes | - | PostgreSQL connection string |
| APP_ENV | No | development | development, staging, production |
| DEBUG | No | false | Enable debug logging |
| CORS_ORIGINS | No | * | Comma-separated allowed origins |
| ML_ENABLED | No | false | Enable ML endpoints |
| WEIGHTS_PATH | If ML | weights/dinov3_classifier.pt | Path to model weights |
| MODEL_DEVICE | No | auto | cpu, cuda, mps |

---

## Appendix: Quick Reference

### Seating a Walk-in

```bash
# 1. Get recommendation
curl -X POST /api/v1/restaurants/{rid}/routing/recommend \
  -H "Content-Type: application/json" \
  -d '{"party_size": 4, "table_preference": "booth"}'

# 2. Seat at recommended table
curl -X POST "/api/v1/restaurants/{rid}/routing/seat?table_id=X&waiter_id=Y&party_size=4"
```

### Seating from Waitlist

```bash
# 1. Add to waitlist
curl -X POST /api/v1/restaurants/{rid}/waitlist \
  -d '{"party_name": "Smith", "party_size": 4}'

# 2. Get recommendation (uses waitlist preferences)
curl -X POST /api/v1/restaurants/{rid}/routing/recommend \
  -d '{"waitlist_id": "entry-uuid"}'

# 3. Seat (marks waitlist as seated)
curl -X POST "/api/v1/restaurants/{rid}/routing/seat?table_id=X&waiter_id=Y&party_size=4&waitlist_id=entry-uuid"
```

### Processing Payment and Clearing

```bash
# 1. Record payment
curl -X POST "/api/v1/visits/{vid}/payment?subtotal=100&tax=9&total=109&tip=22"

# 2. Clear table (sets table to dirty)
curl -X POST /api/v1/visits/{vid}/clear
```

### ML Table State Update

```bash
# From camera system
curl -X POST /ml/predict \
  -F "file=@frame.jpg" \
  -F "table_id=table-uuid"
```

---

*Generated for Restaurant Intelligence Platform v1.0.0*
