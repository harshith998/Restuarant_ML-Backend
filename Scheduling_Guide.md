# Scheduling System Guide

Complete guide for the Restaurant Intelligence Platform's AI-powered scheduling system.

---

## Quick Start with Mimosas

Seed the Mimosas demo restaurant with full scheduling data:

```python
from app.services.seed_service import SeedService
from app.database import get_session_context

async with get_session_context() as session:
    seed = SeedService(session)
    result = await seed.ensure_mimosas_restaurant()
    print(f"Restaurant ID: {result['restaurant_id']}")
```

This creates:
- **Mimosas** brunch restaurant (LA timezone)
- **5 staff**: Maria (server), James (server), Emily (server), Carlos (bartender), Sophie (host)
- **11 tables** across Main Dining, Outdoor Patio, and Bar
- **41 menu items** with pricing and costs
- **60 days** of historical shifts, visits, and orders
- **Staff availability** and **preferences** pre-configured
- **Staffing requirements** for brunch hours (7am-3pm)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Scheduling System                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Staff      │    │   Staffing   │    │   Demand     │      │
│  │ Availability │    │ Requirements │    │  Forecaster  │      │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│         │                   │                    │               │
│         └───────────────────┼────────────────────┘               │
│                             │                                    │
│                             ▼                                    │
│                   ┌─────────────────┐                           │
│                   │   Scheduling    │                           │
│                   │     Engine      │                           │
│                   └────────┬────────┘                           │
│                            │                                     │
│         ┌──────────────────┼──────────────────┐                 │
│         ▼                  ▼                  ▼                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Fairness    │  │  Preference  │  │   Schedule   │          │
│  │  Calculator  │  │   Matcher    │  │  Reasoning   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Models

### Staff Availability
```
StaffAvailability
├── waiter_id (FK)
├── day_of_week (0=Mon, 6=Sun)
├── start_time / end_time
├── availability_type: available | unavailable | preferred
├── effective_from / effective_until (date ranges)
└── notes
```

### Staff Preferences
```
StaffPreference
├── waiter_id (FK)
├── preferred_roles: [server, bartender, host, busser, runner]
├── preferred_shift_types: [morning, afternoon, evening, closing]
├── preferred_sections: [section_ids]
├── max_shifts_per_week / max_hours_per_week / min_hours_per_week
├── avoid_clopening (bool)
└── notes
```

### Staffing Requirements
```
StaffingRequirements
├── restaurant_id (FK)
├── day_of_week
├── start_time / end_time
├── role (server, bartender, host, busser, runner)
├── min_staff / max_staff
├── is_prime_shift (bool)
├── effective_from / effective_until
└── notes
```

### Schedule & Items
```
Schedule
├── restaurant_id (FK)
├── week_start_date
├── status: draft | published | archived
├── generated_by: manual | engine | suggestion
├── version (increments on republish)
└── items[]

ScheduleItem
├── schedule_id (FK)
├── waiter_id (FK)
├── role / section_id
├── shift_date / shift_start / shift_end
├── source: manual | engine | suggestion
├── preference_match_score
└── fairness_impact_score
```

---

## API Endpoints

### Staff Availability

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/staff/{waiter_id}/availability` | List availability patterns |
| POST | `/api/v1/staff/{waiter_id}/availability` | Create availability |
| POST | `/api/v1/staff/{waiter_id}/availability/bulk` | Bulk create availability |
| PATCH | `/api/v1/availability/{id}` | Update availability |
| DELETE | `/api/v1/availability/{id}` | Delete availability |

### Staff Preferences

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/staff/{waiter_id}/preferences` | Get preferences |
| POST | `/api/v1/staff/{waiter_id}/preferences` | Create/update preferences |

### Staffing Requirements

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/restaurants/{id}/staffing-requirements` | List requirements |
| POST | `/api/v1/restaurants/{id}/staffing-requirements` | Create requirement |
| PATCH | `/api/v1/staffing-requirements/{id}` | Update requirement |
| DELETE | `/api/v1/staffing-requirements/{id}` | Delete requirement |

### Schedules

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/restaurants/{id}/schedules` | List schedules |
| POST | `/api/v1/restaurants/{id}/schedules` | Create draft schedule |
| GET | `/api/v1/schedules/{id}` | Get schedule with items |
| PATCH | `/api/v1/schedules/{id}` | Update schedule status |
| POST | `/api/v1/schedules/{id}/publish` | Publish schedule |
| GET | `/api/v1/schedules/{id}/audit` | Get version history |

### Schedule Items

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/schedules/{id}/items` | Add shift to schedule |
| PATCH | `/api/v1/schedule-items/{id}` | Update shift |
| DELETE | `/api/v1/schedule-items/{id}` | Remove shift |

### Scheduling Engine

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/restaurants/{id}/schedules/run` | Run AI scheduling engine |
| GET | `/api/v1/schedule-runs/{id}` | Get run status |

---

## Scheduling Engine Algorithm

The engine uses a **score-and-rank** approach:

### 1. Load Inputs
- Staff availability patterns
- Staff preferences
- Staffing requirements
- Historical demand data (visits)

### 2. Generate Demand Forecast
```python
forecast = demand_forecaster.forecast_week(restaurant_id, week_start)
# Returns predicted covers per day with trend direction
```

### 3. For Each Required Slot

**a) Filter Available Candidates**
- Has availability for this time slot
- Not already assigned at this time
- Under max hours/shifts limits

**b) Score Each Candidate**
```
Total Score = Σ(weight × component_score)

Components:
- Constraint Satisfaction (40%): Availability match
- Preference Match (30%): Role, shift type, section preferences
- Fairness Impact (30%): Hours balance (favors underserved staff)
```

**c) Rank and Assign**
- Sort by total score descending
- Assign top candidate to slot
- Generate reasoning for assignment

### 4. Output
```json
{
  "run_status": "completed",
  "summary_metrics": {
    "items_created": 45,
    "total_hours": 320.5,
    "coverage_pct": 98.2,
    "fairness_gini": 0.12,
    "preference_avg": 72.5
  }
}
```

---

## Fairness Calculation

Uses **Gini coefficient** to measure hours distribution equality:

| Gini | Rating | Interpretation |
|------|--------|---------------|
| < 0.10 | Excellent | Very equal distribution |
| 0.10-0.20 | Good | Minor variation |
| 0.20-0.30 | Fair | Some imbalance |
| > 0.30 | Poor | Significant inequality |

```python
# Example: Calculate fairness impact
fairness_calc = FairnessCalculator()
impact = fairness_calc.calculate_assignment_impact(staff_contexts, new_assignment)
# Returns positive score for underserved staff, negative for overserved
```

---

## Frontend Integration Flow

### 1. Setup Prerequisites
```javascript
// Load requirements
const requirements = await fetch(`/api/v1/restaurants/${id}/staffing-requirements`);

// Load staff availability & preferences
for (const staff of staffList) {
  const availability = await fetch(`/api/v1/staff/${staff.id}/availability`);
  const preferences = await fetch(`/api/v1/staff/${staff.id}/preferences`);
}
```

### 2. Generate Schedule
```javascript
// Trigger engine
const response = await fetch(`/api/v1/restaurants/${id}/schedules/run`, {
  method: 'POST',
  body: JSON.stringify({ week_start_date: '2024-01-15' })
});

const run = await response.json();

// Poll for completion (if needed)
while (run.run_status === 'running') {
  await sleep(2000);
  const status = await fetch(`/api/v1/schedule-runs/${run.id}`);
  run = await status.json();
}

// Get generated schedule
const schedules = await fetch(`/api/v1/restaurants/${id}/schedules?week_start=2024-01-15`);
const schedule = await fetch(`/api/v1/schedules/${schedules[0].id}`);
```

### 3. Review & Edit
```javascript
// Display schedule items with scores
for (const item of schedule.items) {
  console.log(`${item.waiter_id} - ${item.shift_date} ${item.shift_start}-${item.shift_end}`);
  console.log(`  Preference Match: ${item.preference_match_score}%`);
  console.log(`  Fairness Impact: ${item.fairness_impact_score > 0 ? '+' : ''}${item.fairness_impact_score}`);
}

// Make manual adjustments
await fetch(`/api/v1/schedule-items/${itemId}`, {
  method: 'PATCH',
  body: JSON.stringify({ shift_start: '10:00:00' })
});

// Add new shift
await fetch(`/api/v1/schedules/${scheduleId}/items`, {
  method: 'POST',
  body: JSON.stringify({
    waiter_id: 'uuid',
    role: 'server',
    shift_date: '2024-01-15',
    shift_start: '07:00:00',
    shift_end: '15:00:00',
    source: 'manual'
  })
});
```

### 4. Publish
```javascript
await fetch(`/api/v1/schedules/${scheduleId}/publish`, { method: 'POST' });
```

### 5. Analytics
```javascript
// Get schedule performance
const analytics = await fetch(
  `/api/v1/restaurants/${id}/analytics/schedule/${scheduleId}`
);
// Returns coverage %, fairness metrics, preference scores
```

---

## Mimosas Staff Configuration

| Staff | Role | Available Days | Preferences |
|-------|------|----------------|-------------|
| Maria Garcia | Server | Mon, Tue, Thu-Sun | Main Dining, Patio; morning/closing |
| James Wilson | Server | Tue-Sat | Avoids clopening |
| Emily Chen | Server | Mon-Wed, Fri-Sun | Patio; morning only |
| Carlos Rodriguez | Bartender | Mon, Wed-Sun | Bar section |
| Sophie Kim | Host | Every day | 6 shifts max |

### Staffing Requirements (Brunch)

**Weekdays (Mon-Thu)**
- 7am-11am: 2 servers, 1 bartender, 1 host
- 11am-3pm: 3 servers (prime), 1 bartender, 1 host

**Friday**
- 7am-11am: 2 servers
- 11am-3pm: 4 servers (prime)

**Weekend (Sat-Sun)**
- 7am-11am: 3 servers (prime)
- 11am-3pm: 5 servers (prime), 2 bartenders (prime)

---

## Error Handling

| Code | Meaning |
|------|---------|
| 400 | Invalid request (validation error) |
| 404 | Resource not found |
| 409 | Conflict (schedule already exists for week) |
| 422 | Business rule violation |

**Example Error Response:**
```json
{
  "detail": "A schedule already exists for week starting 2024-01-15"
}
```

---

## Cold Start Handling

When no data exists yet:

```javascript
// Availability - returns empty array
GET /api/v1/staff/{id}/availability
→ []

// Preferences - returns null
GET /api/v1/staff/{id}/preferences
→ null

// Schedules - returns empty array
GET /api/v1/restaurants/{id}/schedules
→ []

// Analytics - returns defaults
GET /api/v1/restaurants/{id}/analytics/schedule/{id}/coverage
→ { "coverage_pct": 100.0, "total_slots_required": 0, ... }
```

---

## Testing

Run scheduling tests:
```bash
# All scheduling tests
pytest tests/test_scheduling.py tests/test_scheduling_engine.py -v

# Integration tests with Mimosas
pytest tests/test_scheduling_integration.py -v
```

**Test Coverage:**
- 28 schema validation tests
- 18 engine algorithm tests
- 19 integration tests
- **Total: 65 scheduling tests**

---

## Files Reference

| File | Purpose |
|------|---------|
| `app/api/scheduling.py` | REST endpoints |
| `app/schemas/scheduling.py` | Pydantic schemas |
| `app/models/scheduling.py` | SQLAlchemy models |
| `app/services/scheduling_engine.py` | Main engine |
| `app/services/scheduling_constraints.py` | Constraint checking |
| `app/services/fairness_calculator.py` | Gini & fairness |
| `app/services/demand_forecaster.py` | Demand prediction |
| `app/services/schedule_reasoning.py` | Assignment reasoning |
| `app/services/seed_service.py` | Mimosas seeding |

---

## Related Docs

- `Frontend_Call_Guide_Scheduling_Analytics.md` - Detailed API examples
- `Frontend_Analytics_Guide.md` - Analytics endpoints
- `Scheduling_Analytics_PRD.md` - Product requirements
