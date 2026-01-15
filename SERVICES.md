# External Services Specification

This document outlines services that are **outside the scope of the main PRD** but are required for the full Restaurant Intelligence Platform to function.

---

## 1. Cropper/Segmentation Service (External)

**Purpose:** Produce crop JSON for each camera and re-segment when tables move.

### Responsibilities
- Ingest a video source (RTSP/HTTP/local path)
- Generate crop JSON for all detected table regions
- Periodically re-run segmentation when layout changes
- Return crop JSON to the Crop Service

### Output Contract

Use the crop JSON schema defined in `restaurant-automation-backend/crop_service_prd.md`.

### Requirements
- **Frequency:** On-demand + periodic refresh (configurable)
- **Latency:** Initial segmentation < 10s per camera
- **Stability:** Preserve table ordering when layout stable

---

## 2. Table State Classification Service (External)

**Purpose:** Classify table states and person counts from crops.

### Responsibilities
- Accept crops from the Crop Service
- Classify table states: `clean`, `occupied`, `dirty`
- Count persons at each table (verify party size)
- Push state updates to main API

### Input Contract

Use the classifier dispatch payload defined in `restaurant-automation-backend/crop_service_prd.md`.

### Output Contract

Must push to `POST /api/v1/webhooks/ml/table-state`:

```json
{
  "restaurant_id": "uuid",
  "timestamp": "2025-01-15T18:30:00Z",
  "tables": [
    {
      "table_id": "uuid",
      "table_number": "T1",
      "predicted_state": "occupied",
      "state_confidence": 0.94,
      "person_count": 3,
      "person_count_confidence": 0.87
    },
    {
      "table_id": "uuid",
      "table_number": "T2",
      "predicted_state": "clean",
      "state_confidence": 0.99,
      "person_count": 0,
      "person_count_confidence": 1.0
    }
  ]
}
```

### Requirements
- **Frequency:** Push updates every ~30 seconds (configurable)
- **Latency:** State change detection within 60 seconds of actual change
- **Accuracy targets:**
  - State classification: > 95%
  - Person count: > 90% (within ±1 person)

### Table State Definitions

| State | Visual Criteria |
|-------|-----------------|
| `clean` | Table cleared, no people, ready for seating |
| `occupied` | People seated at table |
| `dirty` | People left, dishes/items remain |

### Integration Notes for ML Team

1. **Table mapping:** Main API will provide table IDs and camera-to-table mapping
2. **Backup role:** Host action is primary for seating; ML confirms and catches misses
3. **Discrepancy handling:** If host marks seated but ML doesn't detect occupancy within 2 min, flag for review
4. **Person count usage:**
   - Verify party size matches check-in
   - Track cumulative covers per waiter for fairness
   - Surface discrepancies (e.g., party of 2 checked in, 4 detected)

### Table Combination Support

If tables can be combined:
```json
{
  "table_id": "uuid",
  "table_number": "T1+T2",
  "is_combined": true,
  "component_tables": ["T1", "T2"],
  "predicted_state": "occupied",
  "person_count": 8
}
```

---

## 3. POS Integration Service

**Purpose:** Receive payment and order data from external POS systems.

### Supported POS Systems (Priority)
1. Toast
2. Square
3. Clover
4. (Others as needed)

### Responsibilities
- Listen for webhooks from POS systems
- Normalize data to standard format
- Forward to main API

### Output Contract

Must push to `POST /api/v1/webhooks/pos/payment`:

```json
{
  "restaurant_id": "uuid",
  "pos_system": "toast",
  "transaction_id": "toast_txn_12345",
  "table_number": "T5",
  "check_number": "1042",
  "timestamp": "2025-01-15T19:45:00Z",

  "subtotal": 78.50,
  "tax": 6.28,
  "total": 84.78,
  "tip": 17.00,
  "payment_method": "credit_card",

  "items": [
    {
      "pos_item_id": "burger_classic",
      "name": "Classic Burger",
      "category": "Entrees",
      "quantity": 2,
      "unit_price": 16.00,
      "total_price": 32.00,
      "modifiers": ["no onions", "extra cheese"]
    },
    {
      "pos_item_id": "fries_large",
      "name": "Large Fries",
      "category": "Sides",
      "quantity": 2,
      "unit_price": 5.50,
      "total_price": 11.00
    }
  ]
}
```

### Event Types to Capture

| Event | When to Send |
|-------|--------------|
| `check_opened` | New check started (optional, for timing) |
| `items_ordered` | Items added to check (for first-served timing) |
| `payment_complete` | Check closed and paid |
| `void` | Item or check voided (for 86 detection) |

### Integration Notes

1. **Table matching:** Use `table_number` to match to internal table records
2. **Visit linking:** Main API will match payment to active visit on that table
3. **Menu item sync:** First time an item is seen, main API creates `menu_items` record
4. **Split checks:** Send separate payment events for each split

---

## 4. Waiter Notification Service

**Purpose:** Push real-time notifications to waiter devices.

### Trigger Events (from Main API)

Main API will emit events via internal message queue:

```json
{
  "event": "table_assigned",
  "waiter_id": "uuid",
  "payload": {
    "table_number": "B2",
    "section": "A",
    "party_size": 4,
    "party_name": "Johnson",
    "notes": "Birthday dinner",
    "assigned_at": "2025-01-15T18:30:00Z"
  }
}
```

### Notification Types

| Event | Message |
|-------|---------|
| `table_assigned` | "New table: B2 - Party of 4 (Johnson)" |
| `table_transferred` | "Table T3 transferred to you from Alice" |
| `shift_ending_soon` | "Your shift ends in 30 min - 2 active tables" |
| `break_reminder` | "You're due for a break" |

### Delivery Channels
- Push notification (mobile app)
- SMS fallback (if app not installed)
- In-app banner (if app is open)

### Requirements
- Delivery latency: < 5 seconds from event
- Delivery confirmation tracking
- Quiet hours / DND respect

---

## 5. LLM Intelligence Layer (Future)

**Purpose:** Natural language insights and recommendations.

### Planned Capabilities

1. **Natural language queries**
   - "How was last Friday dinner service?"
   - "Which servers are struggling this month?"
   - "What's trending on the menu?"

2. **Proactive recommendations**
   - "Consider 86'ing the salmon - 3 voids in last hour"
   - "Section B is getting slammed - consider moving Carol over"
   - "Based on pace, you may want to call in another server"

3. **Anomaly detection**
   - Unusual tip patterns
   - Turn time outliers
   - Unexpected slow periods

### Architecture (Proposed)

```
Main API ──▶ Analytics Data ──▶ LLM Service ──▶ Insights
                                    │
                                    ▼
                            Manager Dashboard
```

### Input Data

LLM will query main API analytics endpoints:
- `/analytics/live`
- `/analytics/daily`
- `/waiters/{id}/analytics`
- `/menu/analytics`

### Output Format

```json
{
  "insight_type": "recommendation",
  "confidence": 0.85,
  "title": "Consider 86'ing Salmon",
  "detail": "3 voids in the last hour, down to 2 portions based on order velocity",
  "suggested_action": "86_item",
  "action_payload": { "item_id": "salmon_grilled" },
  "supporting_data": {
    "recent_voids": 3,
    "estimated_remaining": 2,
    "avg_orders_per_hour": 4
  }
}
```

---

## 6. Frontend Applications

### 5.1 Host Stand App

**Platform:** iPad / tablet web app

**Core screens:**
- Floor view (table states, current assignments)
- Waitlist queue
- Seating flow (select party → see recommendation → confirm)
- Wait time display

**Real-time requirements:**
- WebSocket connection for instant updates
- < 1 second UI refresh on state changes

### 5.2 Manager Dashboard

**Platform:** Web app (desktop-first)

**Core screens:**
- Live floor overview
- Shift performance metrics
- Waiter rankings / analytics
- Historical reports
- Staffing insights / forecasting
- Settings / configuration

### 5.3 Waiter App

**Platform:** Mobile (iOS/Android)

**Core screens:**
- Current tables (with party info, time seated)
- Shift summary (covers, tips, pace)
- Notification center
- Clock in/out, break

**Lightweight focus:**
- Minimal interaction required
- Primarily receives push info
- Quick glance metrics

---

## 7. Service Communication

### Internal Event Bus

Services communicate via message queue (Redis Streams, RabbitMQ, or similar):

```
┌─────────────────┐
│   Main API      │
│  (PostgreSQL)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Message Queue  │
└────────┬────────┘
         │
    ┌────┴────┬─────────────┐
    ▼         ▼             ▼
┌───────┐ ┌───────┐   ┌──────────┐
│Notif. │ │ LLM   │   │Analytics │
│Service│ │Service│   │ Worker   │
└───────┘ └───────┘   └──────────┘
```

### Event Schema

```json
{
  "event_id": "uuid",
  "event_type": "visit.started",
  "timestamp": "2025-01-15T18:30:00Z",
  "restaurant_id": "uuid",
  "payload": { ... },
  "metadata": {
    "source": "main_api",
    "version": "1.0"
  }
}
```

### Event Types

| Event | Consumers |
|-------|-----------|
| `table.state_changed` | Notification, LLM |
| `visit.started` | Notification, Analytics |
| `visit.ended` | Analytics, LLM |
| `payment.received` | Analytics |
| `waiter.assigned` | Notification |
| `shift.started` | Analytics |
| `shift.ended` | Analytics |
| `alert.triggered` | Notification, Dashboard |

---

## 8. Deployment Topology

```
                    ┌─────────────────┐
                    │   Load Balancer │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   Main API      │ │   Main API      │ │   Main API      │
│   Instance 1    │ │   Instance 2    │ │   Instance N    │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼────────┐
                    │   PostgreSQL    │
                    │   (Primary)     │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   PostgreSQL    │
                    │   (Replica)     │
                    └─────────────────┘

         ┌───────────────────────────────────────┐
         │           Background Services          │
         ├─────────────────┬─────────────────────┤
│ Classifier Svc  │  POS Integration    │
│ (GPU Instance)  │  (Webhook receiver) │
         ├─────────────────┼─────────────────────┤
         │  Notification   │  Analytics Worker   │
         │  Service        │  (Cron jobs)        │
         └─────────────────┴─────────────────────┘
```

---

## 9. Development Priority

### Phase 1: Core Platform
1. Main API with PostgreSQL schema
2. Basic routing algorithm
3. ML/CV integration (webhook receiver)
4. Host stand app (MVP)

### Phase 2: Analytics
1. POS integration
2. Waiter metrics computation
3. Manager dashboard
4. Historical reports

### Phase 3: Intelligence
1. Staffing forecasting
2. Real-time alerts
3. Waiter mobile app
4. Menu intelligence

### Phase 4: Advanced
1. LLM layer
2. Predictive features
3. Multi-location analytics
4. Advanced optimizations

---

## 10. Open Questions for Service Teams

### Cropper/Segmentation Team
1. What inputs (RTSP, HLS, file) are supported?
2. What refresh triggers are needed beyond scheduled intervals?
3. How do we keep table IDs stable after small camera shifts?

### Classification Team
1. What accuracy targets are realistic for dirty vs clean?
2. What crop resolution is required for consistent inference?
3. What is the expected response/throughput from the classifier?

### POS Integration Team
1. Which POS systems are customers currently using?
2. Do all target POS systems support webhooks, or do some require polling?
3. How to handle offline POS scenarios?

### Mobile Team
1. Native vs cross-platform for waiter app?
2. Offline support requirements?
3. Device management / MDM considerations?
