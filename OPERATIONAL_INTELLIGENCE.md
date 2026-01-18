# Operational Intelligence Summary

## Review Scraping & Sentiment Analysis
**Files:** `scraper/scraper.py`, `app/services/review_categorization.py`, `app/services/llm_client.py`, `app/api/reviews.py`

- **Yelp Scraper**: Selenium + undetected-chrome driver with anti-bot detection, pagination (up to 5 pages), "Read more" expansion
- **Sentiment Analysis**: ByteDance Seed 1.6 model via OpenRouter API with batch processing (25 reviews/batch)
- **5-Category Opinions**: Food, Service, Atmosphere, Value, Cleanliness — LLM extracts "extreme opinions"
- **Attention Flagging**: `needs_attention` boolean for negative sentiment requiring manager review
- **Pipeline**: Scrape → Ingest JSON → Categorize via LLM → Store with sentiment scores
- **Stats**: Average rating, total count, monthly count, 5-star distribution (pure SQL aggregation)
- **Endpoints**: `/{restaurant_id}/ingest`, `/stats`, `/summary`, `/reviews`, `/categorize`

---

## Menu Intelligence
**Files:** `app/services/menu_optimization_service.py`, `app/services/menu_service.py`, `app/api/menu_analytics.py`

- **Top/Bottom Performers**: Items ranked by combined score = `(demand_score × 0.5) + (margin_pct × 0.5)`
- **Pricing Recommendations**: Matrix of demand (orders/day) vs margin to suggest price changes (±5-15%)
- **86 Recommendations**: Items below score threshold (default 25.0) flagged for removal with reasoning
- **Endpoints**: `/menu/top-sellers`, `/menu/rankings/top`, `/menu/rankings/bottom`, `/menu/pricing-recommendations`, `/menu/86-recommendations`

---

## Server Intelligence
**Files:** `app/services/metrics_aggregator.py`, `app/services/tier_calculator.py`, `app/services/dashboard_service.py`, `app/api/waiter_dashboard.py`

- **Performance Scoring**: Z-score normalized formula: `(turn_time × 0.3) + (tip_pct × 0.4) + (covers × 0.3)`
- **Tier Assignment**: Percentile-based — "strong" (≥p75), "standard" (p25-p75), "developing" (<p25)
- **Turnover Metrics**: `avg_turn_time_minutes`, `min/max_turn_time` from seated→cleared
- **Efficiency**: `(covers_per_shift × 10) / (turn_time / 60)` normalized to percentage
- **6-Month Trends**: Monthly tips, covers, avg tip percentage
- **LLM Insights**: Strengths, areas to watch, suggestions per waiter
- **Endpoints**: `/waiters/{id}/stats`, `/waiters/{id}/trends`, `/waiters/{id}/insights`, `/waiters/{id}/dashboard`

---

## Scheduling Intelligence
**Files:** `app/services/scheduling_engine.py`, `app/services/demand_forecaster.py`, `app/services/fairness_calculator.py`, `app/services/scheduling_constraints.py`

- **Demand Forecasting**: Weighted historical averages with exponential decay (0.85^weeks_ago), linear trend detection
- **Score-and-Rank Algorithm**: `(constraint_score × 0.5) + (fairness_impact × 0.3) + (preference_bonus × 0.2)`
- **Constraint Validation**: Hard (availability, max hours, no overlaps) + Soft (preferences, avoid clopening)
- **Fairness Metrics**: Gini coefficient targeting <0.25, prime shift distribution balance
- **AI Reasoning**: LLM-generated explanations for each shift assignment
- **Endpoints**: `/schedules/run`, `/schedules/{id}`, `/schedule-items/{id}/reasoning`

---

## Analytics & Dashboards
**Files:** `app/services/schedule_analytics.py`, `app/models/metrics.py`, `app/api/analytics.py`

| Metric | Source | Aggregation |
|--------|--------|-------------|
| Table Turn Time | `Visit.duration_minutes` | Per-waiter, restaurant-level |
| Wait Time | `RestaurantMetrics.avg_wait_time_minutes` | Hourly/daily/weekly |
| Peak Hours | `RestaurantMetrics` with hourly period | By day-of-week |
| Revenue Trends | `WaiterMetrics`, `RestaurantMetrics` | Monthly rollups |
| Coverage | `ScheduleAnalyticsService` | % slots filled, understaffed gaps |
| Forecast Accuracy | `DemandForecaster.compare_forecast_to_actual()` | MAPE over 8-12 weeks |

**Key Endpoints:**
- `/analytics/schedule/{id}` — Unified performance metrics
- `/analytics/schedule/{id}/coverage` — Staffing coverage %
- `/analytics/schedule/{id}/fairness` — Gini + hours distribution
- `/analytics/forecasting` — Predicted vs actual covers
- `/analytics/fairness-trends` — Historical fairness over 12 weeks

---

## Data Models
- **WaiterMetrics**: Period-based rollups (shift/daily/weekly/monthly) with turn times, tips, covers
- **RestaurantMetrics**: Aggregate volume, revenue, timing, staffing metrics
- **MenuItemMetrics**: Orders, revenue, hourly distribution per item
- **WaiterInsights**: Cached weekly scores + LLM analysis (strengths, suggestions)
- **ScheduleInsights**: Cached schedule analytics with LLM observations
