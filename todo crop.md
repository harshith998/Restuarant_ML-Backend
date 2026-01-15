# Crop Service TODO

## Done
- Core crop pipeline (capture stub, crop extraction, dispatch, retry/backoff, in-flight limit, dedupe)
- API endpoints for camera management
- Postgres persistence (models, migration, DB-backed registry)
- Unit tests for crop helpers and DB persistence

## Remaining
- RTSP capture support
- Merge/split table identity matching
- Queue-backed dispatch with conflict-safe inserts
- Auth on ingestion endpoints

## Common issues
- Issue: Duplicate dispatch rows -> Cause: multiple schedulers writing same frame -> Mitigation: use conflict-safe insert or idempotent queue
- Issue: Cropper refresh command fails -> Cause: misconfigured command or timeout -> Mitigation: log stderr, verify CROP_REFRESH_COMMAND
- Issue: Camera source unavailable -> Cause: file/URL missing or access denied -> Mitigation: log warning, continue other cameras

---

# Platform-Wide TODO

## Endpoints to Implement

### Tables
- [ ] `GET /api/v1/restaurants/{rid}/tables/available` - List available tables ranked/categorized by type (booth/table) as a map-like view

### Sections
- [ ] `POST /api/v1/restaurants/{rid}/sections` - Create section
- [ ] `PATCH /api/v1/sections/{id}/waiters` - Associate waiters with section
- [ ] `GET /api/v1/restaurants/{rid}/sections` - List sections with assigned waiters

### Camera/Crop Registration
- [ ] `POST /api/v1/tables/{id}/pixel-registration` - Register table with pixel coordinates (x, y, width, height) for camera crop
- [ ] `POST /crops/cameras/{camera_id}/process-and-update` - Crop frame and push all table predictions to DB in one call

---

## Shift & Waiter Improvements

### Scheduled Shifts
- [ ] Add `scheduled_date` field to shifts model
- [ ] Routing should only consider waiters scheduled for TODAY
- [ ] `GET /api/v1/restaurants/{rid}/shifts/scheduled?date=YYYY-MM-DD` - List scheduled shifts for a date

### Load Multiplier (Slow Down Feature)
- [ ] Add `load_factor` field to Shift model (default 1.0, range 0.0-1.0)
- [ ] `PATCH /api/v1/shifts/{id}/load-factor` - Set load factor (e.g., 0.5 = half normal tables)
- [ ] Update routing algorithm: `max_tables_for_waiter = max_tables_per_waiter * load_factor`
- [ ] Use case: Waiter wants to wind down but not go on full break

### Break Endpoint Robustness
- [ ] Track break start/end times
- [ ] Calculate total break duration per shift
- [ ] `GET /api/v1/shifts/{id}/breaks` - List break periods for a shift

---

## Visit Improvements

### POS Integration & Intelligent Calculations
- [ ] Auto-calculate tip percentage from POS data
- [ ] Derive average ticket time from seated_at → payment_at
- [ ] Calculate covers per hour metrics
- [ ] Track items ordered (when menu integration exists)

### Visit Analytics
- [ ] Duration predictions based on party size + table type
- [ ] Flag abnormally long visits (potential issue)
- [ ] Compare actual vs quoted wait times (waitlist → seated)

---

## Waitlist Improvements

### Walk-Away Analytics
- [x] Keep walked_away entries for analytics (already done)
- [ ] Track wait duration before walk-away
- [ ] Calculate walk-away rate by quoted wait time
- [ ] Identify optimal quote threshold to minimize walk-aways

---

## Intelligent Deletion / Data Retention

### Soft Deletes
- [ ] Add `deleted_at` field to core tables (tables, waiters, sections)
- [ ] Filter deleted records by default, allow `?include_deleted=true`
- [ ] Cascade rules: What happens when section deleted but has tables?

### Data Archival
- [ ] Archive visits older than X days to separate table
- [ ] Archive cleared shifts
- [ ] Maintain foreign key integrity during archival

---

## Routing Algorithm

### Current Math (Reference)

**Table Score:**
```
score = 50 (base)
      + 10 if type matches preference
      + 10 if location matches preference
      - 2 × excess_seats
```

**Waiter Priority:**
```
priority = (composite_score × efficiency_weight)
         - (current_tables / max_tables × workload_penalty)
         - (tip_share × tip_penalty)
         - (recency_penalty)
```

### Section Mode
- Waiters assigned to sections
- Tables only assigned if waiter owns that section
- Good for: Large restaurants with distinct areas

### Rotation Mode
- Round-robin across all waiters
- Ignores section assignments
- Good for: Small restaurants, equal distribution focus

### Future Enhancements
- [ ] Consider table turn rate in scoring (fast tables get priority during rush)
- [ ] Weighted preferences (strong preference vs nice-to-have)
- [ ] VIP party handling (skip waitlist, specific waiter assignment)
- [ ] Party size trends (predict wait times based on current occupancy)
- [ ] Hybrid mode: primary section preference but can overflow to other sections
