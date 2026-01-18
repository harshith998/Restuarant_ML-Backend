# Host Demo Replay Guide

This guide describes how the Host app can drive a demo using precomputed
video JSONs and real-time websocket updates.

## Overview
The demo replay system replays table states from precomputed `results.json`
files and updates the database in real time. The Host app subscribes to the
websocket stream and uses the existing routing endpoints for recommendations.

## Demo API

### Start demo replay
`POST /api/v1/demo/initiate`

```json
{
  "restaurant_id": "uuid",
  "speed": 1.0,
  "overwrite": true,
  "mapping_mode": "auto",
  "demos": [
    {
      "camera_id": "cam-3",
      "results_path": "/Users/huntercameronkuperman/Downloads/demovids/3_Mimosas/results.json"
    }
  ]
}
```

Notes:
- `results_path` is repo-root relative by default. Absolute paths are accepted.
- `overwrite=true` means the demo always sets the table state from JSON.
- `speed` can be >1.0 for accelerated playback.

### Optional: seed active shifts + waiters (for host UI)
Pass `seed_shift_snapshot` in the initiate payload to create 4 active waiters,
active shifts, and current visits so the top-of-screen cards have data.

```json
{
  "restaurant_id": "default",
  "speed": 1.0,
  "overwrite": true,
  "mapping_mode": "auto",
  "seed_shift_snapshot": {
    "enabled": true,
    "waiters": [
      { "name": "Sarah", "section_name": "Main Dining", "tier": "strong", "composite_score": 82, "tables_served": 8, "current_tables": 3, "total_tips": 240, "total_covers": 18 },
      { "name": "Tyler", "section_name": "Main Dining", "tier": "standard", "composite_score": 62, "tables_served": 6, "current_tables": 2, "total_tips": 180, "total_covers": 12 },
      { "name": "Maria", "section_name": "Outdoor Patio", "tier": "standard", "composite_score": 58, "tables_served": 6, "current_tables": 2, "total_tips": 165, "total_covers": 10 },
      { "name": "James", "section_name": "Bar", "tier": "developing", "composite_score": 42, "tables_served": 2, "current_tables": 0, "total_tips": 40, "total_covers": 4 }
    ]
  },
  "demos": [
    { "camera_id": "cam-3", "results_path": "/Users/huntercameronkuperman/Downloads/demovids/3_Mimosas/results.json" }
  ]
}
```

Response includes `seeded_waiters` with waiter_id + shift_id for UI use.

### Stop demo replay
`POST /api/v1/demo/stop`

### Demo status
`GET /api/v1/demo/status`

Returns current session state and per-camera progress.

```json
{
  "status": "running",
  "session_id": "uuid",
  "running": true,
  "started_at": "2026-01-18T12:00:00Z",
  "speed": 1.0,
  "cameras": [
    {
      "camera_id": "cam-1",
      "results_path": "...",
      "total_frames": 1200,
      "current_frame_index": 42,
      "last_timestamp_s": 13.7
    }
  ]
}
```

### Host UI summary endpoint (top cards)
`GET /api/v1/restaurants/{restaurant_id}/demo/summary?min_capacity=1`

Returns available tables (clean + active) and ranked waiters using
the existing routing scoring/rotation logic.

```json
{
  "generated_at": "2026-01-18T12:00:00Z",
  "routing_mode": "rotation",
  "open_tables_count": 3,
  "tables": [
    {
      "table_id": "uuid",
      "table_number": "T2",
      "capacity": 4,
      "table_type": "table",
      "location": "inside",
      "section_id": "uuid",
      "section_name": "Main Floor"
    }
  ],
  "waiters": [
    {
      "waiter_id": "uuid",
      "name": "Sarah",
      "tier": "strong",
      "section_id": "uuid",
      "status": "active",
      "current_tables": 3,
      "current_covers": 18,
      "current_tips": 240.0,
      "priority_score": 12.3,
      "rank": 1
    }
  ]
}
```

## WebSocket Stream

Connect to: `ws://<host>/ws/demo`

Event: `table.state`
```json
{
  "type": "table.state",
  "camera_id": "cam-1",
  "table_id": "uuid",
  "table_number": "T3",
  "state": "occupied",
  "confidence": 0.93,
  "timestamp": "2026-01-17T22:32:00Z"
}
```

Optional keepalive messages:
```json
{ "type": "ping" }
```

## Mapping Rules

The demo system maps JSON table numbers to DB table numbers.

1. **Direct match (default)**:
   - If JSON `table_number` set equals DB `table_number` set, map 1:1.
2. **Auto-map** (when mismatch):
   - Sort JSON table numbers and DB table numbers.
   - Map by index order (`json[0] -> db[0]`, `json[1] -> db[1]`, ...).
   - Extra JSON tables are skipped with warnings.
3. **Explicit map override**:
   - Provide `table_map` per demo to override mapping.

Example override:
```json
{
  "camera_id": "cam-1",
  "results_path": "/Users/huntercameronkuperman/Downloads/demovids/3_Mimosas/results.json",
  "table_map": {
    "T0": "1",
    "T1": "2",
    "T2": "3"
  }
}
```

## Routing Recommendations (Reservations + Walk-ins)
Reuse the existing routing endpoint for all recommendations:

`POST /api/v1/restaurants/{restaurant_id}/routing/recommend`

### Request validation (backend)
- Either `party_size` (1-20) or `waitlist_id` must be provided.
- `table_preference`: `booth | bar | table | none`
- `location_preference`: `inside | outside | patio | none`

```json
{
  "party_size": 4,
  "table_preference": "booth",
  "location_preference": "inside"
}
```

### Response shape
```json
{
  "success": true,
  "table_id": "uuid",
  "table_number": "T2",
  "table_type": "table",
  "table_location": "inside",
  "table_capacity": 4,
  "waiter_id": "uuid",
  "waiter_name": "Sarah",
  "section_id": "uuid",
  "section_name": "Main Floor",
  "match_details": {
    "type_matched": true,
    "location_matched": true,
    "capacity_fit": 4
  }
}
```

### Failure responses (common)
```json
{ "success": false, "message": "party_size is required" }
```
```json
{ "success": false, "message": "No available tables for this party size" }
```
```json
{ "success": false, "message": "No available waiters in sections with tables" }
```

This works for reservations and walk-ins. No special reservation routing
endpoint is required.

## Recommended demo flow (frontend + host UI)
1. `POST /api/v1/demo/initiate` with `seed_shift_snapshot.enabled=true`
2. Connect `ws://<host>/ws/demo` for `table.state` updates
3. Poll `GET /api/v1/restaurants/{restaurant_id}/demo/summary` for top cards
4. Use routing endpoint for recommendations
5. For waiter profile cards, call `POST /api/v1/seed/demo` once and then
   fetch `GET /api/v1/waiters/{waiter_id}/dashboard` and
   `GET /api/v1/waiters/{waiter_id}/stats`

## Frontend endpoint checklist
- `POST /api/v1/demo/initiate` (optionally `seed_shift_snapshot`)
- `GET /api/v1/demo/status`
- `GET /api/v1/restaurants/{restaurant_id}/demo/summary?min_capacity=1`
- `ws://<host>/ws/demo` for `table.state` events
- `POST /api/v1/restaurants/{restaurant_id}/routing/recommend`
- `POST /api/v1/seed/demo` then `GET /api/v1/waiters/{waiter_id}/dashboard`
- `GET /api/v1/waiters/{waiter_id}/stats` (and `/trends` if needed)

## Multi-Camera Demos
Provide multiple entries in `demos` to run replay simultaneously:

```json
{
  "restaurant_id": "uuid",
  "demos": [
    { "camera_id": "cam-2", "results_path": "/Users/huntercameronkuperman/Downloads/demovids/2_Mimosas/results.json" },
    { "camera_id": "cam-3", "results_path": "/Users/huntercameronkuperman/Downloads/demovids/3_Mimosas/results.json" },
    { "camera_id": "cam-4", "results_path": "/Users/huntercameronkuperman/Downloads/demovids/4_Mimosas/results.json" },
    { "camera_id": "cam-5", "results_path": "/Users/huntercameronkuperman/Downloads/demovids/5_Mimosas/results.json" },
    { "camera_id": "cam-6", "results_path": "/Users/huntercameronkuperman/Downloads/demovids/6_Mimosas/results.json" },
    { "camera_id": "cam-7", "results_path": "/Users/huntercameronkuperman/Downloads/demovids/7_Mimosas/results.json" },
    { "camera_id": "cam-8", "results_path": "/Users/huntercameronkuperman/Downloads/demovids/8_Mimosas/results.json" },
    { "camera_id": "cam-9", "results_path": "/Users/huntercameronkuperman/Downloads/demovids/9_Mimosas/results.json" },
    { "camera_id": "cam-11", "results_path": "/Users/huntercameronkuperman/Downloads/demovids/11_Mimosas/results.json" }
  ]
}
```

Each camera will emit `table.state` events tagged with its `camera_id`.
For multi-camera demos, provide `table_map` per camera to avoid table number
collisions. Demo floor tables are numeric (`"1"` through `"49"`). Camera 2 has no
annotated tables, so it can omit `table_map`.

### Demo table mappings (per camera)
Use the following `table_map` values to align JSON tables to seeded demo tables:

```json
{
  "restaurant_id": "uuid",
  "demos": [
    {
      "camera_id": "cam-3",
      "results_path": "/Users/huntercameronkuperman/Downloads/demovids/3_Mimosas/results.json",
      "table_map": {
        "T5": "1",
        "T0": "2",
        "T2": "3",
        "T6": "8",
        "T1": "12",
        "T10": "10",
        "T9": "14"
      }
    },
    {
      "camera_id": "cam-4",
      "results_path": "/Users/huntercameronkuperman/Downloads/demovids/4_Mimosas/results.json",
      "table_map": {
        "T6": "23",
        "T4": "21",
        "T1": "24",
        "T5": "20",
        "T0": "22",
        "T2": "15",
        "T3": "11",
        "T8": "14",
        "T7": "10",
        "T9": "9"
      }
    },
    {
      "camera_id": "cam-5",
      "results_path": "/Users/huntercameronkuperman/Downloads/demovids/5_Mimosas/results.json",
      "table_map": {
        "T1": "27",
        "T0": "25",
        "T2": "28",
        "T3": "26"
      }
    },
    {
      "camera_id": "cam-6",
      "results_path": "/Users/huntercameronkuperman/Downloads/demovids/6_Mimosas/results.json",
      "table_map": {
        "T3": "34",
        "T9": "35",
        "T7": "36",
        "T0": "38",
        "T6": "39",
        "T2": "40",
        "T5": "41",
        "T8": "37"
      }
    },
    {
      "camera_id": "cam-7",
      "results_path": "/Users/huntercameronkuperman/Downloads/demovids/7_Mimosas/results.json",
      "table_map": {
        "T2": "43",
        "T0": "44",
        "T4": "46",
        "T5": "47",
        "T3": "48",
        "T1": "49"
      }
    },
    {
      "camera_id": "cam-8",
      "results_path": "/Users/huntercameronkuperman/Downloads/demovids/8_Mimosas/results.json",
      "table_map": {
        "T0": "49"
      }
    }
  ]
}
```