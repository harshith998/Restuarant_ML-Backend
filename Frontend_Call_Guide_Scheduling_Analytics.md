# Frontend Call Guide - Scheduling & Analytics

This document describes how a frontend should call backend APIs for scheduling and analytics.

---

## 1. Staff Availability Endpoints

### 1.1 List Staff Availability
```http
GET /api/v1/staff/{waiter_id}/availability
```
Query params:
- `day_of_week` (optional): Filter by day (0=Monday, 6=Sunday)
- `effective_date` (optional): Filter patterns effective on this date

**Response:**
```json
[
  {
    "id": "uuid",
    "waiter_id": "uuid",
    "restaurant_id": "uuid",
    "day_of_week": 0,
    "start_time": "09:00:00",
    "end_time": "17:00:00",
    "availability_type": "available",  // available | unavailable | preferred
    "effective_from": "2024-01-01",
    "effective_until": null,
    "notes": "Regular weekday availability",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

### 1.2 Create Staff Availability
```http
POST /api/v1/staff/{waiter_id}/availability
```
**Request:**
```json
{
  "day_of_week": 0,
  "start_time": "09:00:00",
  "end_time": "17:00:00",
  "availability_type": "available",
  "effective_from": "2024-01-01",
  "effective_until": null,
  "notes": "Regular availability"
}
```

### 1.3 Bulk Create Availability
```http
POST /api/v1/staff/{waiter_id}/availability/bulk
```
**Request:**
```json
{
  "entries": [
    { "day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00", "availability_type": "available" },
    { "day_of_week": 1, "start_time": "09:00:00", "end_time": "17:00:00", "availability_type": "available" }
  ]
}
```

### 1.4 Update Availability
```http
PATCH /api/v1/availability/{availability_id}
```

### 1.5 Delete Availability
```http
DELETE /api/v1/availability/{availability_id}
```

---

## 2. Staff Preferences Endpoints

### 2.1 Get Staff Preferences
```http
GET /api/v1/staff/{waiter_id}/preferences
```
**Response:**
```json
{
  "id": "uuid",
  "waiter_id": "uuid",
  "restaurant_id": "uuid",
  "preferred_roles": ["server", "bartender"],
  "preferred_shift_types": ["evening", "closing"],
  "preferred_sections": ["uuid1", "uuid2"],
  "max_shifts_per_week": 5,
  "max_hours_per_week": 40,
  "min_hours_per_week": 20,
  "avoid_clopening": true,
  "notes": "Prefers evening shifts",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

### 2.2 Create/Update Staff Preferences
```http
POST /api/v1/staff/{waiter_id}/preferences
```
**Request:**
```json
{
  "preferred_roles": ["server"],
  "preferred_shift_types": ["evening"],
  "preferred_sections": [],
  "max_shifts_per_week": 5,
  "max_hours_per_week": 40,
  "min_hours_per_week": 20,
  "avoid_clopening": true,
  "notes": ""
}
```

---

## 3. Staffing Requirements Endpoints

### 3.1 List Staffing Requirements
```http
GET /api/v1/restaurants/{restaurant_id}/staffing-requirements
```
Query params:
- `day_of_week` (optional): Filter by day (0=Monday, 6=Sunday)
- `role` (optional): Filter by role (server, bartender, host, busser, runner)
- `effective_date` (optional): Filter requirements effective on this date

**Response:**
```json
[
  {
    "id": "uuid",
    "restaurant_id": "uuid",
    "day_of_week": 5,
    "start_time": "17:00:00",
    "end_time": "22:00:00",
    "role": "server",
    "min_staff": 4,
    "max_staff": 6,
    "is_prime_shift": true,
    "effective_from": null,
    "effective_until": null,
    "notes": "Weekend dinner rush",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

### 3.2 Create Staffing Requirement
```http
POST /api/v1/restaurants/{restaurant_id}/staffing-requirements
```
**Request:**
```json
{
  "day_of_week": 5,
  "start_time": "17:00:00",
  "end_time": "22:00:00",
  "role": "server",
  "min_staff": 4,
  "max_staff": 6,
  "is_prime_shift": true,
  "notes": "Weekend dinner rush"
}
```

### 3.3 Update Staffing Requirement
```http
PATCH /api/v1/staffing-requirements/{requirement_id}
```

### 3.4 Delete Staffing Requirement
```http
DELETE /api/v1/staffing-requirements/{requirement_id}
```

---

## 4. Schedule Endpoints

### 4.1 List Schedules
```http
GET /api/v1/restaurants/{restaurant_id}/schedules
```
Query params:
- `week_start` (optional): Filter by week start date
- `status` (optional): Filter by status (draft, published, archived)
- `limit` (optional): Max results (default 10, max 50)

**Response:**
```json
[
  {
    "id": "uuid",
    "restaurant_id": "uuid",
    "week_start_date": "2024-01-08",
    "status": "draft",
    "generated_by": "engine",
    "version": 1,
    "schedule_run_id": "uuid",
    "published_at": null,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
]
```

### 4.2 Create Schedule
```http
POST /api/v1/restaurants/{restaurant_id}/schedules
```
**Request:**
```json
{
  "week_start_date": "2024-01-08",
  "generated_by": "manual"
}
```

### 4.3 Get Schedule with Items
```http
GET /api/v1/schedules/{schedule_id}
```
**Response:**
```json
{
  "id": "uuid",
  "restaurant_id": "uuid",
  "week_start_date": "2024-01-08",
  "status": "draft",
  "generated_by": "engine",
  "version": 1,
  "items": [
    {
      "id": "uuid",
      "schedule_id": "uuid",
      "waiter_id": "uuid",
      "role": "server",
      "section_id": "uuid",
      "shift_date": "2024-01-08",
      "shift_start": "09:00:00",
      "shift_end": "17:00:00",
      "source": "engine",
      "preference_match_score": 85.5,
      "fairness_impact_score": 12.3,
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### 4.4 Update Schedule
```http
PATCH /api/v1/schedules/{schedule_id}
```
**Request:**
```json
{
  "status": "archived"
}
```

### 4.5 Publish Schedule
```http
POST /api/v1/schedules/{schedule_id}/publish
```
Returns updated schedule with `status: "published"` and incremented `version`.

### 4.6 Get Schedule Audit History
```http
GET /api/v1/schedules/{schedule_id}/audit
```
**Response:**
```json
{
  "schedule_id": "uuid",
  "restaurant_id": "uuid",
  "week_start_date": "2024-01-08",
  "history": [
    {
      "version": 2,
      "status": "published",
      "generated_by": "engine",
      "published_at": "2024-01-07T10:00:00Z",
      "created_at": "2024-01-06T10:00:00Z",
      "item_count": 35
    },
    {
      "version": 1,
      "status": "archived",
      "generated_by": "engine",
      "published_at": "2024-01-05T10:00:00Z",
      "created_at": "2024-01-04T10:00:00Z",
      "item_count": 32
    }
  ]
}
```

---

## 5. Schedule Item Endpoints

### 5.1 Add Item to Schedule
```http
POST /api/v1/schedules/{schedule_id}/items
```
**Request:**
```json
{
  "waiter_id": "uuid",
  "role": "server",
  "section_id": "uuid",
  "shift_date": "2024-01-08",
  "shift_start": "09:00:00",
  "shift_end": "17:00:00",
  "source": "manual"
}
```

### 5.2 Update Schedule Item
```http
PATCH /api/v1/schedule-items/{item_id}
```

### 5.3 Delete Schedule Item
```http
DELETE /api/v1/schedule-items/{item_id}
```

---

## 6. Scheduling Engine Endpoints

### 6.1 Run Scheduling Engine
```http
POST /api/v1/restaurants/{restaurant_id}/schedules/run
```
Query params:
- `run_engine` (optional): If true (default), runs engine immediately. If false, creates pending record.

**Request:**
```json
{
  "week_start_date": "2024-01-08"
}
```

**Response (202 Accepted):**
```json
{
  "id": "uuid",
  "restaurant_id": "uuid",
  "week_start_date": "2024-01-08",
  "engine_version": "1.0.0",
  "run_status": "completed",
  "inputs_snapshot": {
    "staff_count": 12,
    "requirements_count": 28,
    "forecast_trend": "increasing",
    "forecast_total_covers": 850
  },
  "summary_metrics": {
    "items_created": 45,
    "total_hours": 320.5,
    "coverage_pct": 98.2,
    "fairness_gini": 0.12,
    "preference_avg": 72.5
  },
  "error_message": null,
  "started_at": "2024-01-07T10:00:00Z",
  "completed_at": "2024-01-07T10:00:05Z",
  "created_at": "2024-01-07T10:00:00Z"
}
```

**Engine Algorithm:**
1. Loads staff availability, preferences, and staffing requirements
2. Generates demand forecast using weighted historical averages + trend prediction
3. For each required time slot, scores available staff by:
   - Constraint satisfaction (availability, max hours, no overlaps)
   - Preference matching (role, shift type, section preferences)
   - Fairness impact (hours balance across staff)
4. Assigns top-scored candidates to each slot
5. Generates reasoning for each assignment

### 6.2 Get Schedule Run Status
```http
GET /api/v1/schedule-runs/{run_id}
```

---

## 7. Frontend Integration Flow

### 7.1 Setup Prerequisites
```
1. GET /api/v1/restaurants/{id}/staffing-requirements
   → Load staffing requirements (coverage config)

2. For each staff member:
   GET /api/v1/staff/{id}/availability
   GET /api/v1/staff/{id}/preferences
   → Load availability and preferences
```

### 7.2 Generate Schedule
```
1. POST /api/v1/restaurants/{id}/schedules/run
   → Trigger scheduling engine

2. Poll GET /api/v1/schedule-runs/{run_id}
   → Wait for run_status === "completed" (poll every 2-5 seconds)

3. GET /api/v1/schedules/{schedule_id}
   → Load generated schedule with items
```

### 7.3 Review and Edit Schedule
```
1. Display schedule items with:
   - Staff name, role, shift times
   - preference_match_score (higher = better fit)
   - fairness_impact_score (positive = improves balance)

2. Allow manual edits:
   PATCH /api/v1/schedule-items/{id}  → Update item
   DELETE /api/v1/schedule-items/{id} → Remove item
   POST /api/v1/schedules/{id}/items  → Add item

3. Publish when ready:
   POST /api/v1/schedules/{id}/publish
```

### 7.4 View History
```
GET /api/v1/schedules/{id}/audit
→ Display version history for the week
```

---

## 8. Enums Reference

### Availability Types
- `available` - Can work this time
- `unavailable` - Cannot work this time
- `preferred` - Prefers to work this time (higher priority)

### Schedule Status
- `draft` - Being created/edited
- `published` - Finalized and visible to staff
- `archived` - Historical record

### Schedule Source
- `manual` - Created by manager
- `suggestion` - Engine suggestion (not auto-assigned)
- `engine` - Auto-generated by engine

### Run Status
- `pending` - Not started
- `running` - In progress
- `completed` - Finished successfully
- `failed` - Error occurred

### Staff Roles
- `server` - Requires performance tracking (tips, covers, tier)
- `bartender` - Requires performance tracking
- `host` - Availability-only scheduling
- `busser` - Availability-only scheduling
- `runner` - Availability-only scheduling

### Shift Types
- `morning` - 6am-11am start
- `afternoon` - 11am-4pm start
- `evening` - 4pm-9pm start
- `closing` - 9pm+ start

---

## 9. Error Handling

| Code | Meaning |
|------|---------|
| 400 | Invalid request (validation error) |
| 404 | Resource not found |
| 409 | Conflict (e.g., schedule already exists for week) |
| 422 | Unprocessable entity (business rule violation) |
| 500 | Internal server error |

---

## 10. Polling and Caching Recommendations

| Resource | Recommendation |
|----------|---------------|
| Schedule run status | Poll every 2-5 seconds until completed |
| Schedule list | Refresh on demand or every 30 seconds |
| Staff availability | Cache for session, refresh on edit |
| Staffing requirements | Cache for session, refresh on edit |
