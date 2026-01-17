# Ben - Video Pipeline Brainstorm

This doc captures everything we might need for the video pipeline, frontend
video creation, and automated screenshot extraction. It also lists concrete
tasks for Ben plus open questions for you.

## Existing Context (Docs + Code)
- `PRD.md`: no explicit video pipeline; only ML/CV integration and live analytics/websocket updates.
- `features.md`: raw CCTV video input, per-table video cropping, ML classification every N frames.
- `SERVICES.md`: external cropper/segmentation service ingests RTSP/HTTP/local sources and returns crop JSON.
- **Already implemented crop service** in this repo:
  - `app/ml/crop_service.py` + `app/ml/crop_api.py`
  - Camera registration, crop JSON updates, periodic frame capture from HTTP/local images,
    crop extraction, classifier dispatch, retry/backoff, in-flight limiting.
  - **Not yet** true live video decode (RTSP/HLS) or frontend video upload pipeline.
  - `todo crop.md` / `progress crop.md`: RTSP capture + table merge/split still pending.

## Goals
- Support **both** live camera sync (RTSP/HLS) and frontend-uploaded videos.
- Backend accepts videos, stores them, and triggers processing jobs.
- Automatically extract screenshots/frames (configurable cadence).
- Track processing status + errors and surface to frontend.
- Provide artifacts (frames, metadata) for downstream ML or UI use.
- Ben decides the exact live vs upload implementation and documents the tradeoffs.

## Scope (initial)
- Live video ingestion (RTSP/HLS) for periodic frame capture.
- Frontend upload for user-supplied videos.
- Validate and store original video.
- Extract frames + key metadata.
- Persist outputs and provide access URLs.
- Trigger tasks for downstream processing (e.g., ML inference).

## Non-goals (unless requested)
- Advanced video editing in frontend (filters, trims, overlays).
- Full media asset management system.
- Real-time streaming playback in-app (beyond basic status + previews).

## Proposed Data Flows
### A) Live Camera Sync (RTSP/HLS)
1. Register camera with video source + crop JSON (or refresh from external cropper).
2. Crop service captures frames on a cadence and extracts table crops.
3. Crops dispatched to classifier; results flow to table-state updates.
4. Frontend receives live state updates via websocket/polling.

### B) Frontend Upload Flow
1. Frontend records/uploads video (direct or pre-signed).
2. Backend stores video, creates job, schedules processing.
3. Worker extracts frames + metadata (cadence or keyframes).
4. Frames stored + indexed; status updates pushed to frontend.
5. Optional: route extracted frames into existing classifier pipeline.

## Camera Onboarding + Crop Preview UI (MVP)
- Camera registry flow: list cameras, add/register, and verify connectivity.
- Initial view: show latest snapshot per camera and the current crop overlays.
- Allow numbering/renaming cameras and mapping to restaurant/section.
- Provide a guided “initial registration” flow so cameras are set up once and
  clearly visible before live processing starts.
- Store a “last known good” snapshot for each camera to validate setup.

## Artifacts to Store
- Original video file.
- Extracted frames (jpg/png).
- Frame metadata (timestamp, index, resolution).
- Video metadata (duration, fps, codec, size).
- Processing logs / errors.

## Storage + Access Patterns
- Video storage: local disk, S3, or other blob store.
- Frame storage: separate bucket/prefix for easy cleanup.
- Access URLs: pre-signed or internal.
- Retention policy and cleanup jobs.

## Processing Requirements
- Frame sampling rate (e.g., 1 fps, 2 fps, or custom).
- Keyframe extraction (optional).
- Thumbnail generation (first frame / best frame).
- Safe timeouts + retry strategy.
- Ability to resume partial processing.

## API + Integration Touchpoints
- POST video upload endpoint.
- GET job status endpoint.
- GET frames list / metadata endpoint.
- Webhook or websocket updates for progress.
- Frontend events: upload progress, status updates, failure reason.

## Frontend Responsibilities
- Provide UI for video capture/upload.
- Validate file size/type before upload.
- Call backend endpoints in correct order.
- Show progress, processing status, and errors.
- Display screenshots/frames in UI.

## Backend Responsibilities
- Validate uploads (type, size, duration).
- Store metadata in DB.
- Schedule async processing.
- Manage retries and failures.
- Provide access control to assets.

## Monitoring + Reliability
- Job status transitions (queued -> processing -> done/failed).
- Detailed error logs.
- Metrics for job duration, failure rate.
- Alerts for stuck jobs.

## Security + Compliance
- Access control on video + frame URLs.
- Rate limits / quotas.
- Data retention + deletion workflows.

## Tasks for Ben (initial list)
- Document current crop service behavior and limits (already implemented).
- Decide live sync (RTSP/HLS) vs upload pipeline details; write tradeoffs.
- Draft API endpoints + payload schema for:
  - video upload
  - job status
  - frames list
- Add camera onboarding + crop preview UI spec:
  - list/register cameras, show initial snapshot + crop overlay,
    assign camera numbers and names
- Define DB models for:
  - video jobs
  - frames metadata
  - processing status
- Specify how frontend uploads feed into classifier/crop pipeline (if any).
- Prototype background job for frame extraction (ffmpeg/OpenCV).
- Evaluate storage approach (local vs S3) and path conventions.
- Outline frontend integration steps and required API sequence.
- Reference pending items in `todo crop.md` / `progress crop.md`:
  - RTSP capture support
  - Merge/split table identity matching
- Write a minimal doc on error handling and retries.
- Add independent detection pipeline notes:
  - hazard detection model (spill/hazard) separate from table-state flow
  - input source (live frames vs uploaded video) and reporting path

## Leveraged Questions (for Ben + You)
1. Live sync approach: RTSP, HLS, or periodic snapshot URL?
2. For uploads: direct backend vs pre-signed object storage?
3. Expected max video size + duration for uploads?
4. Frame sampling rate for live vs upload (same or different)?
5. Need keyframe extraction or uniform sampling only?
6. Should extracted frames be routed into existing classifier pipeline?
7. Retention policy for uploads and extracted frames?
8. Status updates: polling vs websocket; required granularity?
9. Any compliance/security requirements for stored videos?
10. Which frontend stack is this integrating with?
11. Camera onboarding: who assigns camera numbers, and when?
12. Do we need a manual crop editor/adjuster in the onboarding UI?
13. Hazard detection: alert channel (dashboard, push, webhook)?
14. Reservation merge detection: what signals drive merges and where to surface?

