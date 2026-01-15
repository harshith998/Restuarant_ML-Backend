# Crop Service Progress

## Status
- Phase 1 core flow: in progress
- Phase 1 API wiring: complete
- Refresh hook: complete (command-driven)

## Checklist
- [x] JSON state registry for cameras
- [x] Frame capture stub (HTTP/local image)
- [x] Crop extraction from rotated bbox (axis-aligned fallback)
- [x] Classifier dispatch with retry/backoff
- [x] Per-camera in-flight limiting
- [x] Idempotent dispatch per table/frame
- [x] API endpoints for camera management
- [x] Unit tests for crop helpers and state store
- [ ] RTSP capture support (future)
- [ ] Merge/split table matching (future)
- [ ] Postgres persistence (Phase 2)

## Common issues
- Issue: Crop bounds invalid or empty -> Cause: rotated bbox missing/out of frame -> Mitigation: log warning, clamp to frame, skip invalid
- Issue: Classifier dispatch fails -> Cause: endpoint unreachable or timeout -> Mitigation: retry with capped backoff, log failure
- Issue: Camera source unavailable -> Cause: file/URL missing or access denied -> Mitigation: log warning, continue other cameras
- Issue: Duplicate dispatch for same frame -> Cause: repeated scheduler tick or restart -> Mitigation: per-table frame_index dedupe
- Issue: Refresh command fails -> Cause: misconfigured command or timeout -> Mitigation: log stderr, verify CROP_REFRESH_COMMAND
