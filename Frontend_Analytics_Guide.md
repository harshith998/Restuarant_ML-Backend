# Frontend Analytics Guide

This guide covers the Analytics & Insights API endpoints added in Agent 2. These endpoints provide schedule performance analytics, forecast accuracy tracking, fairness trends, and LLM-enhanced insights.

## Quick Start

1. Ensure you have a restaurant with seeded data (see `/api/v1/seed/demo`)
2. Create and publish a schedule using the scheduling endpoints
3. Call the analytics endpoints to get performance metrics

## Base URL

All endpoints are prefixed with `/api/v1`

---

## Endpoints Overview

| Endpoint | Description |
|----------|-------------|
| `GET /restaurants/{id}/analytics/schedule/{schedule_id}` | Unified performance metrics |
| `GET /restaurants/{id}/analytics/schedule/{schedule_id}/coverage` | Coverage metrics |
| `GET /restaurants/{id}/analytics/schedule/{schedule_id}/fairness` | Fairness metrics |
| `GET /restaurants/{id}/analytics/schedule/{schedule_id}/preferences` | Preference match |
| `GET /restaurants/{id}/analytics/schedule/{schedule_id}/insights` | LLM insights |
| `GET /restaurants/{id}/analytics/forecasting?week_start=YYYY-MM-DD` | Forecast accuracy |
| `GET /restaurants/{id}/analytics/forecasting/trends` | Accuracy trends |
| `GET /restaurants/{id}/analytics/fairness-trends` | Fairness history |

---

## 1. Unified Schedule Performance

Get all analytics for a schedule in one call.

**Request:**
```
GET /api/v1/restaurants/{restaurant_id}/analytics/schedule/{schedule_id}?use_llm=true
```

**Query Parameters:**
- `use_llm` (boolean, default: true) - Whether to generate LLM summary

**Response (populated):**
```json
{
  "schedule_id": "550e8400-e29b-41d4-a716-446655440000",
  "week_start": "2024-01-15",
  "status": "published",
  "coverage": {
    "schedule_id": "550e8400-e29b-41d4-a716-446655440000",
    "week_start": "2024-01-15",
    "total_slots_required": 35,
    "total_slots_filled": 32,
    "coverage_pct": 91.4,
    "daily_coverage": [
      {
        "date": "2024-01-15",
        "day_of_week": 0,
        "day_name": "Monday",
        "slots_required": 5,
        "slots_filled": 5,
        "coverage_pct": 100.0
      }
    ],
    "shift_coverage": {
      "morning": 95.0,
      "evening": 88.0
    },
    "understaffed_slots": [
      {
        "date": "2024-01-19",
        "day_name": "Friday",
        "start_time": "17:00:00",
        "end_time": "23:00:00",
        "role": "server",
        "required": 4,
        "filled": 3,
        "shortfall": 1
      }
    ]
  },
  "fairness": {
    "schedule_id": "550e8400-e29b-41d4-a716-446655440000",
    "week_start": "2024-01-15",
    "gini_coefficient": 0.18,
    "gini_rating": "good",
    "hours_std_dev": 4.2,
    "prime_shift_gini": 0.15,
    "is_balanced": true,
    "fairness_issues": [],
    "staff_metrics": [
      {
        "waiter_id": "123e4567-e89b-12d3-a456-426614174000",
        "name": "Alice",
        "weekly_hours": 32.0,
        "hours_vs_target": 0.0,
        "prime_shifts_count": 2,
        "fairness_score": 52.5
      }
    ]
  },
  "preferences": {
    "schedule_id": "550e8400-e29b-41d4-a716-446655440000",
    "avg_preference_score": 85.5,
    "role_match_pct": 95.0,
    "shift_type_match_pct": 80.0,
    "section_match_pct": 75.0,
    "by_staff": [
      {
        "waiter_id": "123e4567-e89b-12d3-a456-426614174000",
        "name": "Alice",
        "preference_score": 90.0,
        "role_matched": true,
        "shift_type_matched": true,
        "section_matched": false,
        "shifts_assigned": 5
      }
    ]
  },
  "insights": {
    "schedule_id": "550e8400-e29b-41d4-a716-446655440000",
    "week_start": "2024-01-15",
    "generated_at": "2024-01-16T10:30:00Z",
    "total_insights": 3,
    "critical_count": 0,
    "warning_count": 2,
    "info_count": 1,
    "coverage_insights": [
      {
        "category": "coverage",
        "severity": "warning",
        "message": "Friday evening coverage is low at 75%",
        "affected_staff_count": 0,
        "affected_staff_names": [],
        "metric_value": 75.0,
        "recommendation": "Add more staff for Friday evening"
      }
    ],
    "fairness_insights": [],
    "pattern_insights": [],
    "llm_summary": "The schedule has good overall coverage at 91.4%. Consider adding one more server for Friday evening to meet peak demand.",
    "llm_model": "bytedance-seed/seed-1.6"
  }
}
```

**Cold Start Response (no schedule items):**
```json
{
  "schedule_id": "550e8400-e29b-41d4-a716-446655440000",
  "week_start": "2024-01-15",
  "status": "draft",
  "coverage": {
    "schedule_id": "550e8400-e29b-41d4-a716-446655440000",
    "week_start": "2024-01-15",
    "total_slots_required": 0,
    "total_slots_filled": 0,
    "coverage_pct": 100.0,
    "daily_coverage": [],
    "shift_coverage": {},
    "understaffed_slots": []
  },
  "fairness": {
    "schedule_id": "550e8400-e29b-41d4-a716-446655440000",
    "week_start": "2024-01-15",
    "gini_coefficient": 0.0,
    "gini_rating": "excellent",
    "hours_std_dev": 0.0,
    "prime_shift_gini": 0.0,
    "is_balanced": true,
    "fairness_issues": [],
    "staff_metrics": []
  },
  "preferences": {
    "schedule_id": "550e8400-e29b-41d4-a716-446655440000",
    "avg_preference_score": 100.0,
    "role_match_pct": 100.0,
    "shift_type_match_pct": 100.0,
    "section_match_pct": 100.0,
    "by_staff": []
  },
  "insights": {
    "schedule_id": "550e8400-e29b-41d4-a716-446655440000",
    "week_start": "2024-01-15",
    "generated_at": "2024-01-16T10:30:00Z",
    "total_insights": 0,
    "critical_count": 0,
    "warning_count": 0,
    "info_count": 0,
    "coverage_insights": [],
    "fairness_insights": [],
    "pattern_insights": [],
    "llm_summary": null,
    "llm_model": null
  }
}
```

---

## 2. Coverage Metrics

Get detailed coverage analysis.

**Request:**
```
GET /api/v1/restaurants/{restaurant_id}/analytics/schedule/{schedule_id}/coverage
```

**Response:**
```json
{
  "schedule_id": "550e8400-e29b-41d4-a716-446655440000",
  "week_start": "2024-01-15",
  "total_slots_required": 35,
  "total_slots_filled": 32,
  "coverage_pct": 91.4,
  "daily_coverage": [
    {
      "date": "2024-01-15",
      "day_of_week": 0,
      "day_name": "Monday",
      "slots_required": 5,
      "slots_filled": 5,
      "coverage_pct": 100.0
    }
  ],
  "shift_coverage": {
    "morning": 95.0,
    "afternoon": 90.0,
    "evening": 88.0,
    "closing": 85.0
  },
  "understaffed_slots": [
    {
      "date": "2024-01-19",
      "day_name": "Friday",
      "start_time": "17:00:00",
      "end_time": "23:00:00",
      "role": "server",
      "required": 4,
      "filled": 3,
      "shortfall": 1
    }
  ]
}
```

**Cold Start (no staffing requirements):**
```json
{
  "schedule_id": "550e8400-e29b-41d4-a716-446655440000",
  "week_start": "2024-01-15",
  "total_slots_required": 0,
  "total_slots_filled": 0,
  "coverage_pct": 100.0,
  "daily_coverage": [],
  "shift_coverage": {},
  "understaffed_slots": []
}
```

---

## 3. Fairness Metrics

Get hour distribution fairness.

**Request:**
```
GET /api/v1/restaurants/{restaurant_id}/analytics/schedule/{schedule_id}/fairness
```

**Response:**
```json
{
  "schedule_id": "550e8400-e29b-41d4-a716-446655440000",
  "week_start": "2024-01-15",
  "gini_coefficient": 0.18,
  "gini_rating": "good",
  "hours_std_dev": 4.2,
  "prime_shift_gini": 0.15,
  "is_balanced": true,
  "fairness_issues": [],
  "staff_metrics": [
    {
      "waiter_id": "123e4567-e89b-12d3-a456-426614174000",
      "name": "Alice",
      "weekly_hours": 32.0,
      "hours_vs_target": 0.0,
      "prime_shifts_count": 2,
      "fairness_score": 52.5
    },
    {
      "waiter_id": "223e4567-e89b-12d3-a456-426614174001",
      "name": "Bob",
      "weekly_hours": 28.0,
      "hours_vs_target": -4.0,
      "prime_shifts_count": 1,
      "fairness_score": 45.0
    }
  ]
}
```

**Gini Rating Scale:**
| Gini | Rating |
|------|--------|
| < 0.10 | excellent |
| 0.10 - 0.19 | good |
| 0.20 - 0.29 | fair |
| >= 0.30 | poor |

---

## 4. Preference Match Metrics

Get how well assignments match staff preferences.

**Request:**
```
GET /api/v1/restaurants/{restaurant_id}/analytics/schedule/{schedule_id}/preferences
```

**Response:**
```json
{
  "schedule_id": "550e8400-e29b-41d4-a716-446655440000",
  "avg_preference_score": 85.5,
  "role_match_pct": 95.0,
  "shift_type_match_pct": 80.0,
  "section_match_pct": 75.0,
  "by_staff": [
    {
      "waiter_id": "123e4567-e89b-12d3-a456-426614174000",
      "name": "Alice",
      "preference_score": 90.0,
      "role_matched": true,
      "shift_type_matched": true,
      "section_matched": false,
      "shifts_assigned": 5
    }
  ]
}
```

**Note:** If staff have no preferences set, all matches return 100%.

---

## 5. LLM-Enhanced Insights

Get AI-generated insights about schedule issues.

**Request:**
```
GET /api/v1/restaurants/{restaurant_id}/analytics/schedule/{schedule_id}/insights?use_llm=true&force_refresh=false
```

**Query Parameters:**
- `use_llm` (boolean, default: true) - Generate LLM summary
- `force_refresh` (boolean, default: false) - Bypass cache

**Response:**
```json
{
  "schedule_id": "550e8400-e29b-41d4-a716-446655440000",
  "week_start": "2024-01-15",
  "generated_at": "2024-01-16T10:30:00Z",
  "total_insights": 4,
  "critical_count": 1,
  "warning_count": 2,
  "info_count": 1,
  "coverage_insights": [
    {
      "category": "coverage",
      "severity": "critical",
      "message": "Overall coverage is critically low at 78%",
      "affected_staff_count": 0,
      "affected_staff_names": [],
      "metric_value": 78.0,
      "recommendation": "Add more staff assignments to meet minimum requirements"
    }
  ],
  "fairness_insights": [
    {
      "category": "fairness",
      "severity": "warning",
      "message": "Hours distribution is somewhat unequal (Gini: 0.28)",
      "affected_staff_count": 0,
      "affected_staff_names": [],
      "metric_value": 0.28,
      "recommendation": "Consider balancing hours among staff"
    }
  ],
  "pattern_insights": [
    {
      "category": "pattern",
      "severity": "warning",
      "message": "2 clopening pattern(s) detected (2 staff affected)",
      "affected_staff_count": 0,
      "affected_staff_names": ["Alice", "Bob"],
      "metric_value": 2.0,
      "recommendation": "Ensure at least 10 hours between closing and opening shifts"
    }
  ],
  "llm_summary": "The schedule has coverage issues requiring immediate attention. Two staff members have clopening patterns that should be addressed for worker wellness.",
  "llm_model": "bytedance-seed/seed-1.6"
}
```

**Insight Severities:**
- `critical` - Immediate action required (coverage < 80%, etc.)
- `warning` - Should be reviewed (coverage 80-90%, Gini > 0.25)
- `info` - General observations

---

## 6. Forecast Accuracy (MAPE)

Compare forecasted demand to actual covers.

**Request:**
```
GET /api/v1/restaurants/{restaurant_id}/analytics/forecasting?week_start=2024-01-08
```

**Query Parameters:**
- `week_start` (date, required) - Monday of week to analyze (must be past)

**Response:**
```json
{
  "week_start": "2024-01-08",
  "restaurant_id": "123e4567-e89b-12d3-a456-426614174000",
  "mape": 15.3,
  "mape_rating": "good",
  "total_predicted_covers": 450.0,
  "total_actual_covers": 420,
  "variance_pct": 7.1,
  "daily_accuracy": [
    {
      "date": "2024-01-08",
      "day_name": "Monday",
      "predicted_covers": 55.0,
      "actual_covers": 52,
      "absolute_error": 3.0,
      "percentage_error": 5.8
    }
  ]
}
```

**MAPE Rating Scale:**
| MAPE | Rating |
|------|--------|
| < 10% | excellent |
| 10-19% | good |
| 20-29% | fair |
| >= 30% | poor |

**Cold Start (no visits):**
```json
{
  "week_start": "2024-01-08",
  "restaurant_id": "123e4567-e89b-12d3-a456-426614174000",
  "mape": 0.0,
  "mape_rating": "excellent",
  "total_predicted_covers": 0.0,
  "total_actual_covers": 0,
  "variance_pct": 0.0,
  "daily_accuracy": []
}
```

---

## 7. Forecast Accuracy Trends

Get historical accuracy over multiple weeks.

**Request:**
```
GET /api/v1/restaurants/{restaurant_id}/analytics/forecasting/trends?weeks=8
```

**Query Parameters:**
- `weeks` (int, default: 8, range: 4-26) - Weeks of history

**Response:**
```json
{
  "restaurant_id": "123e4567-e89b-12d3-a456-426614174000",
  "weeks": [
    {
      "week_start": "2024-01-01",
      "mape": 22.5,
      "mape_rating": "fair",
      "actual_covers": 380
    },
    {
      "week_start": "2024-01-08",
      "mape": 15.3,
      "mape_rating": "good",
      "actual_covers": 420
    }
  ],
  "avg_mape": 18.9,
  "trend_direction": "improving"
}
```

**Trend Directions:**
- `improving` - MAPE decreasing (getting more accurate)
- `stable` - MAPE roughly constant
- `declining` - MAPE increasing (getting less accurate)

---

## 8. Fairness Trends

Get historical fairness across published schedules.

**Request:**
```
GET /api/v1/restaurants/{restaurant_id}/analytics/fairness-trends?weeks=12
```

**Query Parameters:**
- `weeks` (int, default: 12, range: 4-52) - Weeks of history

**Response:**
```json
{
  "restaurant_id": "123e4567-e89b-12d3-a456-426614174000",
  "trends": [
    {
      "week_start": "2024-01-01",
      "gini_coefficient": 0.28,
      "hours_std_dev": 6.5,
      "prime_shift_gini": 0.30,
      "is_balanced": false,
      "staff_count": 8
    },
    {
      "week_start": "2024-01-08",
      "gini_coefficient": 0.18,
      "hours_std_dev": 4.2,
      "prime_shift_gini": 0.15,
      "is_balanced": true,
      "staff_count": 8
    }
  ],
  "avg_gini": 0.23,
  "trend_direction": "improving",
  "weeks_analyzed": 2
}
```

**Cold Start (no published schedules):**
```json
{
  "restaurant_id": "123e4567-e89b-12d3-a456-426614174000",
  "trends": [],
  "avg_gini": 0.0,
  "trend_direction": "stable",
  "weeks_analyzed": 0
}
```

---

## Error Handling

**404 - Schedule Not Found:**
```json
{
  "detail": "Schedule not found"
}
```

**403 - Schedule Doesn't Belong to Restaurant:**
```json
{
  "detail": "Schedule does not belong to this restaurant"
}
```

**400 - Invalid week_start:**
```json
{
  "detail": "week_start must be a Monday"
}
```

**400 - Future week:**
```json
{
  "detail": "Can only analyze completed weeks"
}
```

---

## Frontend Integration Tips

### 1. Loading States

Always show loading states while fetching analytics:
```javascript
const [loading, setLoading] = useState(true);
const [analytics, setAnalytics] = useState(null);

useEffect(() => {
  fetchAnalytics(scheduleId)
    .then(data => setAnalytics(data))
    .finally(() => setLoading(false));
}, [scheduleId]);
```

### 2. Empty State Handling

Check for empty data before rendering:
```javascript
if (analytics.coverage.daily_coverage.length === 0) {
  return <EmptyState message="No staffing requirements defined" />;
}
```

### 3. Severity-Based Styling

Color-code insights by severity:
```javascript
const severityColors = {
  critical: 'red',
  warning: 'orange',
  info: 'blue'
};
```

### 4. Refresh After Schedule Changes

Re-fetch analytics when schedule is modified:
```javascript
const handleScheduleUpdate = async () => {
  await updateSchedule(scheduleId, changes);
  // Force refresh insights
  const insights = await fetchInsights(scheduleId, { force_refresh: true });
  setAnalytics(prev => ({ ...prev, insights }));
};
```

### 5. LLM Summary Fallback

Handle cases where LLM is unavailable:
```javascript
{analytics.insights.llm_summary ? (
  <p>{analytics.insights.llm_summary}</p>
) : (
  <p>
    {analytics.insights.critical_count} critical issues,
    {analytics.insights.warning_count} warnings
  </p>
)}
```

---

## Startup Behavior

When the app starts:

1. **Default data is seeded** in development mode (see `SeedService`)
2. **Tables are created** automatically via `create_all()`
3. **No schedules exist** initially - create via scheduling endpoints
4. **No visits exist** initially - seed demo data for forecast testing

### To test analytics with data:

```bash
# 1. Seed demo data
curl -X POST http://localhost:8000/api/v1/seed/demo

# 2. Create a schedule
curl -X POST http://localhost:8000/api/v1/restaurants/{id}/schedules \
  -H "Content-Type: application/json" \
  -d '{"week_start_date": "2024-01-15"}'

# 3. Run the scheduling engine
curl -X POST http://localhost:8000/api/v1/restaurants/{id}/schedules/run \
  -H "Content-Type: application/json" \
  -d '{"week_start": "2024-01-15"}'

# 4. Get analytics
curl http://localhost:8000/api/v1/restaurants/{id}/analytics/schedule/{schedule_id}
```
