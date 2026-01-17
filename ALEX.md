# ALEX.md - Review Management Feature

## Overview

Build a review management system that aggregates reviews from platforms (Yelp, Google, Opentable), uses AI to categorize and analyze them, and surfaces actionable insights for restaurant managers.

**Key UI Components** (see mockups):
- Filter tabs: All / Needs Attention / Positive
- Review cards with platform badge, star rating, date, text, author, "Respond" button
- Stats sidebar: overall rating, total reviews, this month count, rating distribution (5-star to 1-star), averages by platform
- AI Review Analysis panel: summary text, "What's Working", "Needs Attention", "Recommended Actions"

---

## 5 Services to Implement

| # | Service | Uses LLM? | What It Does |
|---|---------|-----------|--------------|
| 1 | Review Categorization | Yes | Analyze each review individually |
| 2 | Review Ranking | No | Sort/filter reviews for display |
| 3 | AI Summary | Yes | Aggregate insights across all reviews |
| 4 | Platform Stats | No | Calculate numbers and averages |
| 5 | Review Management | No | CRUD operations on reviews |

---

## Technical Details by Service

### Service 1: Review Categorization (LLM)
- **Input**: Single review text + star rating
- **Output**:
  - `sentiment_score`: Float from -1.0 (very negative) to 1.0 (very positive)
  - `categories`: JSON with scores for food, service, ambiance, value, wait_time, cleanliness
  - `needs_attention`: Boolean - TRUE if negative sentiment detected (this powers the "Needs Attention" filter)
- **Trigger**: Run on each new review after ingestion

### Service 2: Review Ranking (No LLM)
- **Ranking factors**:
  - Recency (newer first)
  - Negativity (needs_attention=true prioritized)
  - Star rating
- **Filters**: all, needs_attention, positive (rating >= 4 AND needs_attention=false)

### Service 3: AI Summary (LLM)
- **Input**: All reviews from last 30 days
- **Output**:
  - `summary_text`: "Based on 23 reviews this month, customers love your food quality..."
  - `whats_working`: ["Food quality consistently praised", "Sarah mentioned by name 5 times", ...]
  - `needs_attention`: ["Slow service during peak hours (mentioned 8 times)", ...]
  - `recommended_actions`: ["Consider adding staff during Friday/Saturday 7-9pm rush", ...]

### Service 4: Platform Stats (No LLM)
- Overall average rating (e.g., 4.2)
- Total review count (e.g., 847)
- Reviews this month (e.g., 23)
- Rating distribution: count per star level (5-star: 412, 4-star: 245, etc.)
- By platform averages (Google: 4.3, Yelp: 3.9, Opentable: 4.5)

### Service 5: Review Management (No LLM)
- Bulk ingest reviews (dedupe by `platform_review_id`)
- Mark as responded
- Dismiss/clear review
- Status tracking: pending, needs_response, responded, dismissed

---

## Data Model

**Review** should store:
- `restaurant_id` (FK - multi-tenant)
- `platform` (google/yelp/opentable)
- `platform_review_id` (unique - for deduplication)
- `author_name`, `rating` (1-5), `text`, `review_date`
- `sentiment_score`, `categories` (JSON), `needs_attention` (populated by Service 1)
- `status` (pending/needs_response/responded/dismissed)
- `created_at`, `updated_at`

---

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/reviews/{restaurant_id}/ingest` | Bulk add reviews |
| GET | `/reviews/{restaurant_id}?filter=all\|needs_attention\|positive` | List reviews |
| GET | `/reviews/{restaurant_id}/stats` | Rating stats |
| GET | `/reviews/{restaurant_id}/summary` | AI summary |
| POST | `/reviews/{review_id}/respond` | Mark responded |
| DELETE | `/reviews/{review_id}` | Dismiss review |

---

## Key Decisions (Your Choice)

- **LLM Provider**: OpenAI, Anthropic, Ollama - pick one, abstract it so it's swappable
- **Platform APIs**: Decide which to integrate (Google Places API, Yelp Fusion API, Opentable)
- **Real-time sync**: Consider WebSocket for pushing new reviews to frontend

---

## Files to Create

```
app/models/review.py
app/schemas/review.py
app/services/review_categorization.py  (LLM)
app/services/review_ranking.py
app/services/review_summary.py         (LLM)
app/services/review_stats.py
app/services/review_management.py
app/api/reviews.py
tests/test_reviews.py
```

---

## Best Practices

- Follow existing patterns (check `app/services/waiter.py`, `app/api/tables.py`)
- All models need `restaurant_id` (multi-tenant)
- Async/await for all DB operations
- Type hints everywhere (`from __future__ import annotations`)
- Write curl examples to test endpoints
- Run `alembic revision --autogenerate -m "add reviews"` for migration

---

## Deliverables Checklist

- [ ] Review model + migration
- [ ] Pydantic schemas
- [ ] 5 services (2 with LLM, 3 without)
- [ ] API routes
- [ ] Tests with curl examples
- [ ] **Create FRONTEND_GUIDE.md when backend is complete**
