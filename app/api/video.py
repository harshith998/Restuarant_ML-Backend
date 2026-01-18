"""
REST API endpoints for video upload and processing pipeline.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.video import ExtractedFrame, FrameClassification, VideoJob
from app.schemas.video import (
    ExtractedFrameResponse,
    FrameListResponse,
    TableStateSummary,
    VideoJobResponse,
    VideoJobStatus,
    VideoProcessRequest,
    VideoProcessResponse,
    VideoResultsResponse,
    VideoUploadResponse,
)
from app.services.video_processor import (
    VideoProcessorError,
    process_frames_with_classification,
    process_video_job,
    save_uploaded_video,
    validate_video_file,
)

LOGGER = logging.getLogger("video-api")

router = APIRouter(prefix="/api/v1/videos", tags=["videos"])

# Static files base URL (for frame URLs)
STATIC_BASE = os.getenv("STATIC_BASE_URL", "/static")


@router.post("/upload", response_model=VideoUploadResponse, status_code=201)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    restaurant_id: Optional[str] = Form(None),
    camera_id: Optional[str] = Form(None),
    fps: float = Form(1.0),
    session: AsyncSession = Depends(get_session),
) -> VideoUploadResponse:
    """
    Upload a video file for processing.

    The video will be stored and frames will be extracted in the background.
    Use GET /videos/{job_id} to check processing status.

    Args:
        file: Video file (max 100MB, mp4/mov/avi/mkv/webm)
        restaurant_id: Optional restaurant UUID to link
        camera_id: Optional camera ID to link
        fps: Frame extraction rate (default: 1 fps)
    """
    # Read file content
    content = await file.read()
    file_size = len(content)

    # Validate
    try:
        validate_video_file(file.filename or "video.mp4", file.content_type, file_size)
    except VideoProcessorError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Create job record
    job_id = uuid4()
    job = VideoJob(
        id=job_id,
        restaurant_id=UUID(restaurant_id) if restaurant_id else None,
        camera_id=camera_id,
        original_filename=file.filename or "video.mp4",
        stored_path="",  # Will be updated after save
        file_size_bytes=file_size,
        status="queued",
    )

    # Save file
    try:
        stored_path = await save_uploaded_video(content, file.filename or "video.mp4", job_id)
        job.stored_path = stored_path
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # Save job to DB
    session.add(job)
    await session.commit()
    await session.refresh(job)

    # Start background processing
    background_tasks.add_task(process_video_job, job_id, fps)

    LOGGER.info(f"Video uploaded: job_id={job_id}, file={file.filename}, size={file_size}")

    return VideoUploadResponse(
        job_id=job_id,
        status=VideoJobStatus.QUEUED,
        file_name=file.filename or "video.mp4",
        file_size_bytes=file_size,
        created_at=job.created_at,
    )


@router.get("/{job_id}", response_model=VideoJobResponse)
async def get_job_status(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> VideoJobResponse:
    """
    Get video job status and metadata.

    Poll this endpoint to track processing progress.
    """
    result = await session.execute(
        select(VideoJob).where(VideoJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return VideoJobResponse(
        id=job.id,
        status=VideoJobStatus(job.status),
        progress_percent=job.progress_percent,
        frames_extracted=job.frames_extracted,
        duration_seconds=float(job.duration_seconds) if job.duration_seconds else None,
        fps=float(job.fps) if job.fps else None,
        width=job.width,
        height=job.height,
        codec=job.codec,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
    )


@router.get("/{job_id}/frames", response_model=FrameListResponse)
async def list_frames(
    job_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> FrameListResponse:
    """
    List extracted frames for a video job.

    Returns paginated list of frames with URLs.
    """
    # Check job exists and is completed
    result = await session.execute(
        select(VideoJob).where(VideoJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get total count
    count_result = await session.execute(
        select(func.count()).select_from(ExtractedFrame).where(ExtractedFrame.job_id == job_id)
    )
    total = count_result.scalar() or 0

    # Get frames for page
    offset = (page - 1) * limit
    result = await session.execute(
        select(ExtractedFrame)
        .where(ExtractedFrame.job_id == job_id)
        .order_by(ExtractedFrame.frame_index)
        .offset(offset)
        .limit(limit)
    )
    frames = result.scalars().all()

    # Build frame responses with URLs
    frame_responses = []
    for frame in frames:
        # Convert file path to URL
        # Path: uploads/videos/{job_id}/frames/frame_0001.jpg
        # URL: /static/videos/{job_id}/frames/frame_0001.jpg
        relative_path = frame.file_path.replace("uploads/", "")
        url = f"{STATIC_BASE}/{relative_path}"

        frame_responses.append(ExtractedFrameResponse(
            id=frame.id,
            frame_index=frame.frame_index,
            timestamp_ms=frame.timestamp_ms,
            url=url,
            width=frame.width,
            height=frame.height,
        ))

    return FrameListResponse(
        job_id=job_id,
        total_frames=total,
        page=page,
        limit=limit,
        frames=frame_responses,
    )


@router.get("/{job_id}/frames/{frame_index}/image")
async def get_frame_image(
    job_id: UUID,
    frame_index: int,
    session: AsyncSession = Depends(get_session),
):
    """
    Get a specific frame image by index.

    Returns the JPEG image file directly.
    """
    result = await session.execute(
        select(ExtractedFrame)
        .where(ExtractedFrame.job_id == job_id)
        .where(ExtractedFrame.frame_index == frame_index)
    )
    frame = result.scalar_one_or_none()

    if not frame:
        raise HTTPException(status_code=404, detail="Frame not found")

    if not os.path.exists(frame.file_path):
        raise HTTPException(status_code=404, detail="Frame file not found on disk")

    return FileResponse(
        frame.file_path,
        media_type="image/jpeg",
        filename=f"frame_{frame_index:04d}.jpg",
    )


@router.post("/{job_id}/process", response_model=VideoProcessResponse, status_code=202)
async def process_video(
    job_id: UUID,
    request: VideoProcessRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> VideoProcessResponse:
    """
    Process video frames with table classification.

    Requires either crop_json (table bounding boxes) or camera_id
    (to use existing camera's crop JSON).

    Args:
        job_id: Video job ID
        request: Processing parameters with crop_json or camera_id
    """
    # Check job exists and is completed
    result = await session.execute(
        select(VideoJob).where(VideoJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job not ready for processing (status: {job.status})"
        )

    # Get crop JSON
    crop_json = request.crop_json

    if not crop_json and request.camera_id:
        # Fetch from camera
        from app.models.crop import CameraCropState
        result = await session.execute(
            select(CameraCropState).where(CameraCropState.camera_id == request.camera_id)
        )
        camera_state = result.scalar_one_or_none()

        if not camera_state or not camera_state.crop_json:
            raise HTTPException(
                status_code=404,
                detail=f"No crop JSON found for camera {request.camera_id}"
            )
        crop_json = camera_state.crop_json

    if not crop_json:
        raise HTTPException(
            status_code=400,
            detail="Must provide crop_json or camera_id"
        )

    # Count tables and frames
    tables_count = len(crop_json.get("tables", []))
    frames_to_process = job.frames_extracted // request.process_every_n

    # Generate task ID
    process_task_id = uuid4()

    # Start background processing
    background_tasks.add_task(
        process_frames_with_classification,
        job_id,
        crop_json,
        request.process_every_n,
        request.update_db,
        request.consensus_window,
    )

    LOGGER.info(f"Started classification for job {job_id}: {frames_to_process} frames, {tables_count} tables")

    return VideoProcessResponse(
        job_id=job_id,
        process_task_id=process_task_id,
        status="processing",
        frames_to_process=frames_to_process,
        tables_count=tables_count,
    )


@router.get("/{job_id}/results", response_model=VideoResultsResponse)
async def get_results(
    job_id: UUID,
    include_per_frame: bool = Query(False, description="Include per-frame results (can be large)"),
    session: AsyncSession = Depends(get_session),
) -> VideoResultsResponse:
    """
    Get classification results for a processed video.

    Returns summary of table state changes and optionally per-frame details.
    """
    # Check job exists
    result = await session.execute(
        select(VideoJob).where(VideoJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get classifications
    result = await session.execute(
        select(FrameClassification)
        .where(FrameClassification.job_id == job_id)
        .order_by(FrameClassification.frame_index, FrameClassification.table_number)
    )
    classifications = result.scalars().all()

    if not classifications:
        return VideoResultsResponse(
            job_id=job_id,
            status=VideoJobStatus(job.status),
            frames_processed=0,
            tables_updated=0,
            summary={},
            per_frame_results=[] if include_per_frame else None,
        )

    # Build summary
    summary: dict[str, TableStateSummary] = {}
    per_frame: dict[int, dict] = {}
    tables_updated = set()

    for c in classifications:
        table_num = c.table_number or f"T{c.table_id}"
        smoothed = c.smoothed_state or c.predicted_state

        # Initialize table summary
        if table_num not in summary:
            summary[table_num] = TableStateSummary(
                final_state="unknown",
                final_smoothed_state="unknown",
                state_changes=[],
                smoothed_state_changes=[],
            )

        # Track raw state changes
        prev_changes = summary[table_num].state_changes
        if not prev_changes or prev_changes[-1]["state"] != c.predicted_state:
            prev_changes.append({
                "frame": c.frame_index,
                "state": c.predicted_state,
                "confidence": float(c.confidence),
            })

        # Track smoothed state changes
        prev_smoothed = summary[table_num].smoothed_state_changes
        if not prev_smoothed or prev_smoothed[-1]["state"] != smoothed:
            prev_smoothed.append({
                "frame": c.frame_index,
                "state": smoothed,
            })

        summary[table_num].final_state = c.predicted_state
        summary[table_num].final_smoothed_state = smoothed

        if c.table_id:
            tables_updated.add(c.table_id)

        # Build per-frame results
        if include_per_frame:
            if c.frame_index not in per_frame:
                per_frame[c.frame_index] = {
                    "frame_index": c.frame_index,
                    "timestamp_ms": c.frame_index * 1000,  # Approximate
                    "tables": [],
                }

            per_frame[c.frame_index]["tables"].append({
                "table_id": str(c.table_id) if c.table_id else None,
                "table_number": c.table_number,
                "state": c.predicted_state,
                "confidence": float(c.confidence),
            })

    # Count unique frames processed
    frames_processed = len(set(c.frame_index for c in classifications))

    return VideoResultsResponse(
        job_id=job_id,
        status=VideoJobStatus(job.status),
        frames_processed=frames_processed,
        tables_updated=len(tables_updated),
        summary=summary,
        per_frame_results=list(per_frame.values()) if include_per_frame else None,
    )


@router.post("/{job_id}/visualize")
async def generate_visualization(
    job_id: UUID,
    request: VideoProcessRequest,
    use_smoothed: bool = Query(True, description="Use smoothed states (False for debug)"),
    session: AsyncSession = Depends(get_session),
):
    """
    Generate an annotated video with classification results visualized.

    Returns a downloadable MP4 with colored bounding boxes showing table states:
    - Green = clean
    - Yellow = occupied
    - Red = dirty

    Requires crop_json with table bounding boxes.
    """
    from app.services.video_visualizer import generate_annotated_video_with_crops

    # Check job exists and has classifications
    result = await session.execute(
        select(VideoJob).where(VideoJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get crop JSON
    crop_json = request.crop_json

    if not crop_json and request.camera_id:
        from app.models.crop import CameraCropState
        result = await session.execute(
            select(CameraCropState).where(CameraCropState.camera_id == request.camera_id)
        )
        camera_state = result.scalar_one_or_none()
        if camera_state and camera_state.crop_json:
            crop_json = camera_state.crop_json

    if not crop_json:
        raise HTTPException(
            status_code=400,
            detail="Must provide crop_json or camera_id"
        )

    try:
        output_path = await generate_annotated_video_with_crops(
            job_id=job_id,
            crop_json=crop_json,
            fps=1.0,
            use_smoothed=use_smoothed,
        )

        return FileResponse(
            output_path,
            media_type="video/mp4",
            filename=f"annotated_{job_id}.mp4",
        )
    except Exception as e:
        LOGGER.error(f"Failed to generate visualization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """
    Delete a video job and all associated data.

    This removes the video file, extracted frames, and all DB records.
    """
    import shutil
    from pathlib import Path

    result = await session.execute(
        select(VideoJob).where(VideoJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Delete files
    job_dir = Path(job.stored_path).parent
    if job_dir.exists():
        try:
            shutil.rmtree(job_dir)
        except Exception as e:
            LOGGER.warning(f"Failed to delete job directory: {e}")

    # Delete DB records (cascade will handle frames and classifications)
    await session.delete(job)
    await session.commit()

    LOGGER.info(f"Deleted video job {job_id}")
