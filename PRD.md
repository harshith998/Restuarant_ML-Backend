# Restaurant Intelligence Platform - Product Requirements Document

**Version:** 1.0
**Status:** Draft
**Last Updated:** January 2025

---

## 1. Executive Summary

This document defines the requirements for a **Restaurant Intelligence Platform** - a PostgreSQL-backed data layer and routing API that manages real-time restaurant state, intelligently routes parties to tables and waiters, and captures analytics for operational insights and staffing decisions.

The system is **table-centric** (not party-centric), **fairness-first** in routing, and designed to integrate with external ML/CV services for automated state detection.

---

## 2. Goals

### Primary Goals
- **Persistent State Management:** Replace JSON-based state with PostgreSQL for durability, querying, and scalability
- **Intelligent Routing:** Assign parties to tables and waiters with fairness-first algorithm (update the waiter algorithm in table router and other files)
- **Waiter Analytics:** Auto-calculate waiter performance tiers from real metrics
- **Operational Intelligence:** Provide staffing insights, turn time analytics, and demand forecasting
- **Multi-Location Ready:** Schema supports multiple restaurant locations from day one

### Non-Goals (Out of Scope for v1)
- Guest-facing reservation system (walk-in only for v1)
- Guest satisfaction surveys (separate service)
- Full POS functionality (we receive webhooks, don't process payments)
- LLM-powered recommendations (future intelligence layer)
- Frontend applications (separate development)

---

## 3. User Personas

### Host
- Primary user of routing system
- Checks in parties to waitlist
- Seats tables (assigns waitlisted party to table + waiter)
- Needs real-time floor status

### Manager
- Monitors shift performance
- Reviews waiter analytics and rankings
- Uses staffing insights for scheduling
- Accesses historical reports

### Waiter
- Receives table assignment notifications
- Views current shift summary (tables, covers, tips)
- Lightweight interaction - primarily receives pushes

---

## 4. Core Features

### 4.1 Waitlist Management

**Simple queue system:**
- Party checks in with: name, party size, table preference (booth/bar/table/none)
- System tracks: check-in time, quoted wait time, actual wait time
- Parties can be seated directly from waitlist into routing algorithm
- Track walk-aways for quote accuracy analytics

**Data captured:**
```
- party_name: string
- party_size: int
- table_preference: enum (booth, bar, table, none)
- checked_in_at: timestamp
- quoted_wait_minutes: int (nullable)
- seated_at: timestamp (nullable)
- walked_away_at: timestamp (nullable)
```

### 4.2 Routing Algorithm

**Fairness-first approach with soft constraints:**

1. **Filter available tables:**
   - State = clean (from ML)
   - Capacity >= party size
   - Apply preference if possible (backtrack if not)

2. **Determine valid sections:**
   - Section mode: Only route to tables in sections with available waiters
   - Rotation mode: Any table, round-robin waiter assignment

3. **Score and rank waiters:**
   ```
   priority = (efficiency_score × EFFICIENCY_WEIGHT)
            - (current_tables / max_tables × WORKLOAD_PENALTY)
            - (tip_share × TIP_PENALTY)
            - (recency_penalty)  # soft no-double-seat
   ```

4. **Recency consideration (soft no-double-seat):**
   - Penalize waiters seated recently (last 5-10 min)
   - BUT override if waiter is significantly underserved
   - Not a hard rule - algorithm balances fairness

5. **Select optimal match:**
   - Highest priority waiter
   - Smallest fitting table in their section

**Operating Modes:**
- **Section Mode:** Waiters own sections, tables route within sections
- **Rotation Mode:** Round-robin across all waiters regardless of section
- API endpoint to switch modes per restaurant

### 4.3 Table State Management

**States (from ML/CV service):**
- `clean` - Ready for seating
- `occupied` - Party currently seated
- `dirty` - Needs cleaning
- `reserved` - Held (future use)
- `unavailable` - Out of service

**State transitions:**
```
clean → occupied (host seats table)
occupied → dirty (ML detects party left)
dirty → clean (ML detects cleared/cleaned)
```

**ML/CV Integration:**
- ML service pushes state updates every ~30 seconds
- Host action is primary trigger for seating
- ML serves as confirmation and backup

### 4.4 Visit Tracking

A **visit** represents one table occupancy session:

```
visit_id: uuid
table_id: fk
waiter_id: fk
shift_id: fk
waitlist_entry_id: fk (nullable)

-- Timestamps (milestones)
seated_at: timestamp          # Host seats table
first_served_at: timestamp    # From service integration (future)
payment_at: timestamp         # From POS webhook
cleared_at: timestamp         # ML detects clean

-- Metrics
party_size: int               # From waitlist or ML verification
actual_covers: int            # From ML person count
duration_minutes: int         # Computed: cleared - seated

-- Payment (from POS webhook)
subtotal: decimal
tax: decimal
total: decimal
tip: decimal
payment_method: string
pos_transaction_id: string
```

### 4.5 Waiter Performance & Tiers

**Auto-calculated tiers based on metrics:**

| Tier | Criteria |
|------|----------|
| Strong | Top 25% composite score |
| Standard | Middle 50% |
| Developing | Bottom 25% |

**Metrics tracked:**

| Metric | Window | Purpose |
|--------|--------|---------|
| avg_turn_time | shift, day, week, all-time | Efficiency |
| total_covers | shift, day, week | Workload |
| total_tips | shift, day, week | Performance proxy |
| tip_percentage | rolling | Service quality |
| tables_served | shift, day | Volume |
| avg_check_size | rolling | (future: upselling) |

**Composite score formula:**
```
score = (normalized_turn_time × 0.3)      # Lower is better
      + (normalized_tip_pct × 0.4)        # Higher is better
      + (normalized_covers × 0.3)         # Higher is better
```

Tiers recalculate daily based on rolling 30-day performance.

### 4.6 Shift Management

**Per-shift tracking:**
```
shift_id: uuid
waiter_id: fk
restaurant_id: fk
section_id: fk (nullable - for section mode)

clock_in: timestamp
clock_out: timestamp
status: enum (active, on_break, ended)

-- Shift aggregates (real-time updated)
tables_served: int
total_covers: int
total_tips: decimal
total_sales: decimal
```

**Shift handoff logic:**
- When waiter clocks out with active tables:
  - Tables transfer to designated replacement waiter
  - Visit record tracks `original_waiter_id` and `transferred_to_waiter_id`
  - Tips earned before transfer stay with original waiter

### 4.7 Staffing Intelligence

**Historical Benchmarks:**
```sql
-- "What did last Tuesday look like?"
SELECT
  date,
  total_covers,
  waiter_count,
  avg_turn_time,
  total_revenue
FROM daily_metrics
WHERE restaurant_id = X
  AND day_of_week = 'Tuesday'
ORDER BY date DESC
LIMIT 8;
```

**Demand Forecasting:**
- Track covers by: hour, day of week, month, season
- Identify patterns (Friday dinner rush, Sunday brunch, etc.)
- Surface predictions: "Expecting ~180 covers tonight based on historical Friday average"

**Real-time Alerts:**
- Current pace vs historical average
- Alert when: pace > 120% of staffed capacity
- Alert when: waiters idle (pace < 50% capacity)

### 4.8 Menu Intelligence

**From POS payment webhooks, track:**

```
menu_item_id: uuid
name: string
category: string
price: decimal
cost: decimal (if provided)

-- Analytics (aggregated)
times_ordered: int (by day, week, month)
total_revenue: decimal
avg_per_cover: decimal
peak_hours: jsonb  # {"11-12": 45, "12-13": 89, ...}
day_of_week_distribution: jsonb
```

**Insights surfaced:**
- Top sellers by time period
- Trending up/down items
- Margin analysis (if cost data available)
- Seasonal patterns

**86'd Tracking (lightweight for v1):**
- JSON config file for currently unavailable items
- Future: Auto-detect from void patterns or inventory integration

### 4.9 Manager Analytics Dashboard (API Support)

**Live Floor Status:**
- All tables with current state
- Current waiter assignments
- Waitlist depth and wait times
- Active covers in restaurant

**Shift Performance:**
- Covers seated so far vs pace
- Revenue pace
- Per-waiter breakdown (tables, covers, tips)
- Turn time running average

**Historical Reports:**
- Day/week/month comparisons
- Waiter rankings
- Table utilization rates
- Peak hour analysis

---

## 5. PostgreSQL Schema Design

### 5.1 Core Tables

```sql
-- Multi-location support
CREATE TABLE restaurants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    timezone VARCHAR(50) DEFAULT 'America/New_York',
    config JSONB DEFAULT '{}',  -- routing mode, weights, etc.
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sections within a restaurant
CREATE TABLE sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID REFERENCES restaurants(id),
    name VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Physical tables
CREATE TABLE tables (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID REFERENCES restaurants(id),
    section_id UUID REFERENCES sections(id),
    table_number VARCHAR(20) NOT NULL,  -- "T1", "B3", etc.
    capacity INT NOT NULL,
    table_type VARCHAR(20) NOT NULL,  -- booth, bar, table

    -- Current state (updated by ML)
    state VARCHAR(20) DEFAULT 'clean',  -- clean, occupied, dirty, unavailable
    state_confidence DECIMAL(3,2),
    state_updated_at TIMESTAMPTZ,

    -- Current visit (denormalized for fast access)
    current_visit_id UUID,

    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(restaurant_id, table_number)
);

-- Staff members
CREATE TABLE waiters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID REFERENCES restaurants(id),
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(20),

    -- Performance tier (auto-calculated)
    tier VARCHAR(20) DEFAULT 'standard',  -- strong, standard, developing
    composite_score DECIMAL(5,2) DEFAULT 50.0,
    tier_updated_at TIMESTAMPTZ,

    -- Lifetime stats (for historical context)
    total_shifts INT DEFAULT 0,
    total_covers INT DEFAULT 0,
    total_tips DECIMAL(10,2) DEFAULT 0,

    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Work shifts
CREATE TABLE shifts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID REFERENCES restaurants(id),
    waiter_id UUID REFERENCES waiters(id),
    section_id UUID REFERENCES sections(id),  -- nullable for rotation mode

    clock_in TIMESTAMPTZ NOT NULL,
    clock_out TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'active',  -- active, on_break, ended

    -- Real-time aggregates
    tables_served INT DEFAULT 0,
    total_covers INT DEFAULT 0,
    total_tips DECIMAL(10,2) DEFAULT 0,
    total_sales DECIMAL(10,2) DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Waitlist queue
CREATE TABLE waitlist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID REFERENCES restaurants(id),

    party_name VARCHAR(100),
    party_size INT NOT NULL,
    table_preference VARCHAR(20),  -- booth, bar, table, none
    notes TEXT,

    checked_in_at TIMESTAMPTZ DEFAULT NOW(),
    quoted_wait_minutes INT,

    -- Resolution
    status VARCHAR(20) DEFAULT 'waiting',  -- waiting, seated, walked_away
    seated_at TIMESTAMPTZ,
    walked_away_at TIMESTAMPTZ,

    -- Link to visit when seated
    visit_id UUID,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table visits (occupancy sessions)
CREATE TABLE visits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID REFERENCES restaurants(id),
    table_id UUID REFERENCES tables(id),
    waiter_id UUID REFERENCES waiters(id),
    shift_id UUID REFERENCES shifts(id),
    waitlist_id UUID REFERENCES waitlist(id),

    -- Party info
    party_size INT NOT NULL,  -- From waitlist
    actual_covers INT,        -- From ML person count

    -- Timeline milestones
    seated_at TIMESTAMPTZ NOT NULL,
    first_served_at TIMESTAMPTZ,
    payment_at TIMESTAMPTZ,
    cleared_at TIMESTAMPTZ,

    -- Computed metrics
    duration_minutes INT,

    -- Payment summary (from POS)
    subtotal DECIMAL(10,2),
    tax DECIMAL(10,2),
    total DECIMAL(10,2),
    tip DECIMAL(10,2),
    tip_percentage DECIMAL(5,2),
    pos_transaction_id VARCHAR(100),

    -- Transfer tracking
    original_waiter_id UUID REFERENCES waiters(id),
    transferred_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Menu items (populated from POS)
CREATE TABLE menu_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID REFERENCES restaurants(id),
    pos_item_id VARCHAR(100),  -- External POS ID

    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    price DECIMAL(10,2),
    cost DECIMAL(10,2),  -- If available

    is_available BOOLEAN DEFAULT true,  -- 86'd = false

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(restaurant_id, pos_item_id)
);

-- Order line items (from POS webhooks)
CREATE TABLE order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    visit_id UUID REFERENCES visits(id),
    menu_item_id UUID REFERENCES menu_items(id),

    quantity INT DEFAULT 1,
    unit_price DECIMAL(10,2),
    total_price DECIMAL(10,2),
    modifiers JSONB,

    ordered_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 5.2 Analytics/Metrics Tables

```sql
-- Waiter metrics (pre-computed rollups)
CREATE TABLE waiter_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    waiter_id UUID REFERENCES waiters(id),
    restaurant_id UUID REFERENCES restaurants(id),

    period_type VARCHAR(20) NOT NULL,  -- shift, daily, weekly, monthly
    period_start DATE NOT NULL,
    period_end DATE,
    shift_id UUID REFERENCES shifts(id),  -- For shift-level metrics

    -- Counts
    tables_served INT DEFAULT 0,
    total_covers INT DEFAULT 0,
    total_visits INT DEFAULT 0,

    -- Money
    total_sales DECIMAL(12,2) DEFAULT 0,
    total_tips DECIMAL(10,2) DEFAULT 0,
    avg_tip_percentage DECIMAL(5,2),
    avg_check_size DECIMAL(10,2),

    -- Time
    avg_turn_time_minutes DECIMAL(6,2),
    min_turn_time_minutes DECIMAL(6,2),
    max_turn_time_minutes DECIMAL(6,2),

    computed_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(waiter_id, period_type, period_start, shift_id)
);

-- Restaurant-level metrics
CREATE TABLE restaurant_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID REFERENCES restaurants(id),

    period_type VARCHAR(20) NOT NULL,  -- hourly, daily, weekly, monthly
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ,

    -- Volume
    total_parties INT DEFAULT 0,
    total_covers INT DEFAULT 0,
    peak_occupancy INT,

    -- Revenue
    total_revenue DECIMAL(12,2) DEFAULT 0,
    total_tips DECIMAL(10,2) DEFAULT 0,
    avg_check_size DECIMAL(10,2),

    -- Timing
    avg_turn_time_minutes DECIMAL(6,2),
    avg_wait_time_minutes DECIMAL(6,2),

    -- Staffing
    waiter_count INT,
    covers_per_waiter DECIMAL(6,2),

    computed_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(restaurant_id, period_type, period_start)
);

-- Menu item analytics
CREATE TABLE menu_item_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    menu_item_id UUID REFERENCES menu_items(id),
    restaurant_id UUID REFERENCES restaurants(id),

    period_type VARCHAR(20) NOT NULL,  -- daily, weekly, monthly
    period_start DATE NOT NULL,

    times_ordered INT DEFAULT 0,
    total_revenue DECIMAL(10,2) DEFAULT 0,

    -- Distribution (for pattern analysis)
    hourly_distribution JSONB,  -- {"11": 5, "12": 12, ...}

    computed_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(menu_item_id, period_type, period_start)
);

-- Table state history (for ML accuracy tracking)
CREATE TABLE table_state_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id UUID REFERENCES tables(id),

    previous_state VARCHAR(20),
    new_state VARCHAR(20),
    confidence DECIMAL(3,2),
    source VARCHAR(20),  -- 'ml', 'host', 'system'

    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 5.3 Indexes

```sql
-- Performance indexes
CREATE INDEX idx_tables_restaurant_state ON tables(restaurant_id, state);
CREATE INDEX idx_shifts_waiter_active ON shifts(waiter_id, status) WHERE status = 'active';
CREATE INDEX idx_visits_table_active ON visits(table_id) WHERE cleared_at IS NULL;
CREATE INDEX idx_waitlist_restaurant_waiting ON waitlist(restaurant_id, status) WHERE status = 'waiting';
CREATE INDEX idx_waiter_metrics_lookup ON waiter_metrics(waiter_id, period_type, period_start);
CREATE INDEX idx_restaurant_metrics_lookup ON restaurant_metrics(restaurant_id, period_type, period_start);
CREATE INDEX idx_visits_seated_at ON visits(restaurant_id, seated_at);
CREATE INDEX idx_order_items_visit ON order_items(visit_id);
```

---

## 6. API Endpoints

### 6.1 Routing & Seating

```
POST /api/v1/restaurants/{id}/route
  Body: { waitlist_id: uuid } OR { party_size: int, preference: string }
  Returns: { table_id, waiter_id, section, routing_details }

POST /api/v1/restaurants/{id}/tables/{table_id}/seat
  Body: { waitlist_id: uuid, waiter_id: uuid }
  Returns: { visit_id }

POST /api/v1/restaurants/{id}/mode
  Body: { mode: "section" | "rotation" }
  Returns: { success: bool }
```

### 6.2 State Management

```
GET  /api/v1/restaurants/{id}/floor
  Returns: All tables with current state, active visits, waiter assignments

POST /api/v1/restaurants/{id}/tables/{table_id}/state
  Body: { state: string, source: "host" | "ml", confidence?: float }

GET  /api/v1/restaurants/{id}/waiters/active
  Returns: All clocked-in waiters with current stats

POST /api/v1/restaurants/{id}/waiters/{waiter_id}/clock-in
POST /api/v1/restaurants/{id}/waiters/{waiter_id}/clock-out
POST /api/v1/restaurants/{id}/waiters/{waiter_id}/break
```

### 6.3 Waitlist

```
GET  /api/v1/restaurants/{id}/waitlist
POST /api/v1/restaurants/{id}/waitlist
  Body: { party_name, party_size, table_preference?, notes? }

PATCH /api/v1/restaurants/{id}/waitlist/{entry_id}
  Body: { status: "walked_away" }

DELETE /api/v1/restaurants/{id}/waitlist/{entry_id}
```

### 6.4 Analytics

```
GET /api/v1/restaurants/{id}/analytics/live
  Returns: Current shift stats, pace, occupancy

GET /api/v1/restaurants/{id}/analytics/shift/{shift_id}
GET /api/v1/restaurants/{id}/analytics/daily?date=YYYY-MM-DD
GET /api/v1/restaurants/{id}/analytics/weekly?week_start=YYYY-MM-DD
GET /api/v1/restaurants/{id}/analytics/compare?dates=YYYY-MM-DD,YYYY-MM-DD

GET /api/v1/restaurants/{id}/waiters/{waiter_id}/analytics
  Query: period=shift|daily|weekly|monthly

GET /api/v1/restaurants/{id}/staffing/forecast
  Query: date=YYYY-MM-DD
  Returns: Predicted covers, recommended waiter count

GET /api/v1/restaurants/{id}/menu/analytics
  Query: period=daily|weekly|monthly, top_n=10
```

### 6.5 Webhooks (Inbound)

```
POST /api/v1/webhooks/ml/table-state
  Body: { tables: [{ table_id, predicted_state, confidence, person_count }] }

POST /api/v1/webhooks/pos/payment
  Body: {
    transaction_id,
    table_number,
    subtotal, tax, total, tip,
    items: [{ pos_item_id, name, quantity, price }]
  }
```

### 6.6 WebSocket

```
WS /api/v1/restaurants/{id}/live
  Events:
    - table_state_changed
    - waiter_assigned
    - visit_started
    - visit_ended
    - waitlist_updated
    - alert (staffing, pace)
```

---

## 7. Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL SERVICES                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌──────────────┐         ┌──────────────┐         ┌────────────┐ │
│   │   ML/CV      │         │     POS      │         │   Future   │ │
│   │   Service    │         │   System     │         │   LLM      │ │
│   └──────┬───────┘         └──────┬───────┘         └────────────┘ │
│          │                        │                                 │
│          │ table state            │ payment                         │
│          │ person count           │ webhooks                        │
│          ▼                        ▼                                 │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │                 RESTAURANT INTELLIGENCE API                  │  │
│   │  ┌─────────────────────────────────────────────────────┐    │  │
│   │  │                   PostgreSQL                         │    │  │
│   │  │  • Tables, Visits, Waiters, Shifts                  │    │  │
│   │  │  • Metrics (waiter, restaurant, menu)               │    │  │
│   │  │  • State history                                    │    │  │
│   │  └─────────────────────────────────────────────────────┘    │  │
│   │                                                              │  │
│   │  ┌─────────────────┐    ┌─────────────────┐                 │  │
│   │  │ Routing Engine  │    │ Analytics Engine │                 │  │
│   │  │ • Fairness algo │    │ • Aggregations   │                 │  │
│   │  │ • Section/Rotate│    │ • Forecasting    │                 │  │
│   │  └─────────────────┘    └─────────────────┘                 │  │
│   └──────────────────────────┬──────────────────────────────────┘  │
│                              │                                      │
│          ┌───────────────────┼───────────────────┐                 │
│          ▼                   ▼                   ▼                 │
│   ┌────────────┐      ┌────────────┐      ┌────────────┐          │
│   │   Host     │      │  Manager   │      │  Waiter    │          │
│   │   App      │      │ Dashboard  │      │   App      │          │
│   └────────────┘      └────────────┘      └────────────┘          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 8. Data Retention Policy

| Data Type | Detail Retention | Aggregate Retention |
|-----------|------------------|---------------------|
| Visits | 90 days | 2 years (in metrics tables) |
| Order items | 90 days | 2 years (in menu metrics) |
| Table state log | 30 days | N/A |
| Waiter metrics | N/A | 2 years |
| Restaurant metrics | N/A | 2 years |
| Waitlist entries | 90 days | N/A |

Automated jobs:
- Daily: Compute/update metrics aggregations
- Weekly: Archive old detail records to cold storage
- Monthly: Purge records beyond retention window

---

## 9. Configuration

Per-restaurant config stored in `restaurants.config` JSONB:

```json
{
  "routing": {
    "mode": "section",
    "max_tables_per_waiter": 5,
    "efficiency_weight": 1.0,
    "workload_penalty": 3.0,
    "tip_penalty": 2.0,
    "recency_penalty_minutes": 5,
    "recency_penalty_weight": 1.5
  },
  "alerts": {
    "understaffed_threshold": 1.2,
    "overstaffed_threshold": 0.5
  },
  "shifts": {
    "default_section_assignment": true,
    "allow_cross_section": false
  }
}
```

---

## 10. Success Metrics

| Metric | Target |
|--------|--------|
| Tip variance across waiters (shift) | < 15% deviation from mean |
| Cover variance across waiters (shift) | < 20% deviation from mean |
| Double-seat rate | < 10% of seatings |
| Routing decision latency | < 100ms |
| State sync accuracy (ML vs actual) | > 95% |

---

## 11. Open Questions / Future Considerations

1. **Reservation system** - When needed, extend waitlist with `reserved_at` timestamp and hold logic
2. **Guest profiles** - Link visits to returning guests (requires guest identity system)
3. **LLM layer** - Natural language queries ("How was last Friday?"), smart 86 recommendations
4. **Advanced forecasting** - Weather API integration, local events calendar
5. **Multi-floor support** - Floor as entity between restaurant and section

---

## Appendix A: Waiter Tier Calculation

```python
def calculate_composite_score(waiter_id: str, lookback_days: int = 30) -> float:
    metrics = get_waiter_metrics(waiter_id, period='daily', days=lookback_days)

    # Normalize each metric to 0-100 scale relative to peers
    norm_turn_time = normalize_inverse(metrics.avg_turn_time)  # Lower is better
    norm_tip_pct = normalize(metrics.avg_tip_percentage)       # Higher is better
    norm_covers = normalize(metrics.avg_covers_per_shift)      # Higher is better

    # Weighted composite
    score = (
        norm_turn_time * 0.3 +
        norm_tip_pct * 0.4 +
        norm_covers * 0.3
    )

    return score

def assign_tier(score: float, percentiles: dict) -> str:
    if score >= percentiles['p75']:
        return 'strong'
    elif score >= percentiles['p25']:
        return 'standard'
    else:
        return 'developing'
```

---

## Appendix B: Sample Routing Decision

```
Input:
  - Party size: 4
  - Preference: booth
  - Mode: section

Step 1: Filter tables
  - Clean tables: T1, T2, T5, T8, B1, B2
  - Capacity >= 4: T2, T5, B1, B2
  - Type = booth: B1, B2

Step 2: Valid sections
  - B1 in Section A
  - B2 in Section B
  - Valid sections: {A, B}

Step 3: Available waiters in sections
  - Alice (Section A): 2 tables, $45 tips, score 78
  - Bob (Section B): 3 tables, $62 tips, score 65
  - Carol (Section A): on_break - excluded

Step 4: Score waiters
  - Alice: 78*1.0 - (2/5)*3.0 - (45/107)*2.0 = 78 - 1.2 - 0.84 = 75.96
  - Bob: 65*1.0 - (3/5)*3.0 - (62/107)*2.0 = 65 - 1.8 - 1.16 = 62.04

Step 5: Select
  - Best waiter: Alice (75.96)
  - Best table in Section A: B1 (capacity 4)

Output:
  - Table: B1
  - Waiter: Alice
  - Section: A
```
