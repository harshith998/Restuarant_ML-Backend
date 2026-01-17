# Scheduling & Analytics PRD

**Version:** 0.1  
**Status:** Draft  
**Last Updated:** January 2026

---

## 1. Purpose
Define backend-only requirements for intelligent staff scheduling, preferences, fairness reasoning, and analytics dashboards. This PRD extends existing routing/shift/waiter analytics concepts without duplicating them.

**Referenced sources (do not re-implement here):**
- Core entities, shifts, visits, waiter analytics in `PRD.md`.
- Current API catalog in `API_DOCUMENTATION.md`.
- Early analytics concepts in `features.md`.

---

## 2. Goals
- Generate schedules using historical data and an internal prediction engine.
- Capture staff preferences, availability, constraints, and fairness targets.
- Provide a reasoning layer explaining schedule decisions.
- Deliver analytics suitable for dashboard views (wait times, turn times, revenue, staffing KPIs).
- Offer APIs to create, view, and version schedules and analytics.

## 3. Non-Goals (v1)
- UI/UX implementation.
- External signals (weather/events) as mandatory inputs.
- Fully automated staffing without human approval.
- POS or reservation integrations beyond existing webhook support.

---

## 4. Scope Additions
This PRD introduces **new** data structures, endpoints, and analytics aggregations. Existing shift, waiter, visit, and routing concepts stay as-is and are referenced from current docs.

### 4.1 New Data Entities (high level)
**StaffAvailability**
- `id`, `staff_id`, `restaurant_id`
- `day_of_week`, `start_time`, `end_time`
- `availability_type`: `available | unavailable | preferred`
- `effective_date_range`

**StaffPreference**
- `id`, `staff_id`, `restaurant_id`
- `preferred_roles` (server, host, runner, etc.)
- `preferred_shifts` (e.g., brunch, dinner)
- `preferred_days_off`
- `max_shifts_per_week`, `max_hours_per_week`
- `notes`

**Schedule**
- `id`, `restaurant_id`, `week_start_date`
- `status`: `draft | published | archived`
- `generated_by`: `manual | engine`
- `version`, `created_at`, `published_at`

**ScheduleItem**
- `id`, `schedule_id`, `staff_id`, `role`
- `shift_start`, `shift_end`
- `source`: `manual | suggestion | engine`
- `preference_match_score`, `fairness_impact_score`

**ScheduleRun**
- `id`, `restaurant_id`, `week_start_date`
- `inputs_snapshot_id`
- `engine_version`, `run_status`
- `summary_metrics` (JSON)
- `created_at`

**ScheduleReasoning**
- `id`, `schedule_run_id`, `schedule_item_id`
- `reasons`: list of structured strings
- `constraint_violations` (if any)
- `confidence_score`

**AnalyticsSnapshot**
- `id`, `restaurant_id`, `period_start`, `period_end`
- `metrics` (JSON)
- `generated_at`

---

## 5. Scheduling Engine Specification
### 5.1 Inputs
- Historical visits, covers, turn times, wait times (from existing `visits` and analytics).
- Past schedules and actual attendance (shifts).
- Staff availability and preferences.
- Restaurant staffing requirements (roles, minimum coverage by hour).

### 5.2 Prediction Engine (Historical + Intelligent)
- Use historical demand patterns by hour/day/week.
- Output forecasted demand by time bucket (e.g., hourly covers).
- Provide confidence bands and a reason summary.

### 5.3 Constraints
**Hard constraints:**
- Availability and approved time-off.
- Role eligibility.
- Legal/restaurant max hours per week.

**Soft constraints (weighted):**
- Preference matching (days, roles, shift types).
- Fairness targets (balanced prime shifts, evenly distributed workload).
- Avoid consecutive late/early turnarounds.

### 5.4 Fairness Model (v1)
Fairness is a composite score computed per staff member and aggregated:
- **Workload balance:** hours, tables served, covers.
- **Prime shift balance:** distribution of high-demand slots.
- **Tip opportunity balance:** proxy using historical revenue/covers.

Provide a `fairness_score` per schedule and per staff member.

### 5.5 Reasoning Layer Output
Each schedule item includes:
- Matched preferences (e.g., "prefers Friday nights").
- Constraint satisfaction (e.g., "within 30 hr max").
- Fairness explanation (e.g., "balances prime shifts vs last week").
- Prediction contribution (e.g., "Fri 6-9 forecast high demand").

---

## 6. API Additions (Backend)
These endpoints are **new** and should be added to the existing API catalog:

### Preferences & Availability
- `GET /api/v1/staff/{id}/availability`
- `POST /api/v1/staff/{id}/availability`
- `GET /api/v1/staff/{id}/preferences`
- `POST /api/v1/staff/{id}/preferences`

### Scheduling
- `POST /api/v1/schedules/run`  
  Runs scheduling engine for a week; returns `schedule_run_id`.
- `GET /api/v1/schedules/run/{id}`  
  Fetches run status, summary, and reasoning output.
- `POST /api/v1/schedules`  
  Creates a schedule (manual or from run output).
- `GET /api/v1/schedules/{id}`  
  Retrieves a schedule with items and reasoning.
- `POST /api/v1/schedules/{id}/publish`  
  Publishes a schedule (versioned).
- `GET /api/v1/schedules/{id}/audit`  
  Returns schedule history and changes.

### Analytics (Dashboard)
- `GET /api/v1/analytics/dashboard/overview`
- `GET /api/v1/analytics/dashboard/operations`
- `GET /api/v1/analytics/dashboard/staff`
- `GET /api/v1/analytics/insights`

---

## 7. Analytics & Dashboard Metrics (v1)
Metrics should be time-windowed (day/week/month) and support trend vs prior period.

### 7.1 Core Overview
- Weekly revenue
- Weekly covers
- Average check size
- Week-over-week deltas

### 7.2 Operations
- Table turn time (avg, goal vs actual)
- Wait time by hour (avg, peak, goal)
- Kitchen speed (avg ticket time, tickets over threshold)
- Peak hours heatmap (covers by hour/day)

### 7.3 Staff Analytics
- Staff on shift
- Tables served per staff
- Tips per staff
- Fairness balance score (schedule + actual)

### 7.4 AI Assistant Insights
Generated insights based on anomalies:
- "Turn times 7 min above goal on Tue"
- "Friday 7-9pm demand forecast +25% vs last week"
- "Staffing gap: 1 server shortage 6-10pm"

---

## 8. Agent Split and Dependencies
### Agent 1 — Scheduling Core
- Define schema for availability/preferences/schedule/run/reasoning/audit.
- Specify scheduling engine inputs, constraints, fairness scoring.
- Define scheduling endpoints and response shapes.

### Agent 2 — Analytics + Insights
- Define KPI calculations and aggregation windows.
- Define dashboard endpoints and insight payloads.
- Specify data freshness, caching, and snapshot strategy.

**Shared dependency:** both agents rely on existing shifts, visits, and waiter analytics definitions.

**Completion note:** once tasks are complete, agents should delete any temporary notes or scratch files they created, and delete this PRD file if it was only needed for coordination.

---

## 9. Frontend Feature Guide (separate doc)
A lightweight guide describing how a frontend should call the new scheduling and analytics endpoints, how to render schedule reasoning, and how to fetch insight cards. See `Frontend_Call_Guide_Scheduling_Analytics.md`.

