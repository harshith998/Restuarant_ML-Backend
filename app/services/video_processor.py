"""
Video processing service for frame extraction and classification.

Handles:
- Video metadata extraction (ffprobe)
- Frame extraction (ffmpeg)
- Table crop extraction
- ML classification (DINOv3 or SAM3, configurable via CLASSIFIER_BACKEND env var)
- Database updates
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import cv2
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory as async_session
from app.models.video import ExtractedFrame, FrameClassification, VideoJob
from app.models.table import Table
from app.schemas.video import VideoMetadata

LOGGER = logging.getLogger("video-processor")

# Configuration
UPLOADS_DIR = os.getenv("UPLOADS_DIR", "uploads/videos")
MAX_FILE_SIZE = int(os.getenv("MAX_VIDEO_SIZE_MB", "100")) * 1024 * 1024  # 100MB default
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ALLOWED_CONTENT_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"}


class VideoProcessorError(Exception):
    """Base exception for video processing errors."""
    pass


def get_video_metadata(video_path: str) -> VideoMetadata:
    """
    Extract video metadata using ffprobe.

    Args:
        video_path: Path to the video file

    Returns:
        VideoMetadata with duration, fps, resolution, codec
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        video_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        raise VideoProcessorError(f"ffprobe failed: {e.stderr}") from e
    except json.JSONDecodeError as e:
        raise VideoProcessorError(f"Failed to parse ffprobe output: {e}") from e

    # Find video stream
    video_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if not video_stream:
        raise VideoProcessorError("No video stream found in file")

    # Parse fps (can be "30/1" or "29.97")
    fps_str = video_stream.get("r_frame_rate", "30/1")
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    else:
        fps = float(fps_str)

    # Get duration from format or stream
    duration = float(data.get("format", {}).get("duration", 0))
    if duration == 0:
        duration = float(video_stream.get("duration", 0))

    return VideoMetadata(
        duration_seconds=duration,
        fps=fps,
        width=int(video_stream.get("width", 0)),
        height=int(video_stream.get("height", 0)),
        codec=video_stream.get("codec_name", "unknown"),
    )


def extract_frames(
    video_path: str,
    output_dir: str,
    fps: float = 1.0,
    start_time: float = 0.0,
    end_time: Optional[float] = None,
) -> Tuple[int, List[str]]:
    """
    Extract frames from video using ffmpeg.

    Args:
        video_path: Path to input video
        output_dir: Directory to save frames
        fps: Frames per second to extract (default: 1)
        start_time: Start time in seconds
        end_time: End time in seconds (None = full video)

    Returns:
        Tuple of (frame_count, list of frame paths)
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    cmd = ["ffmpeg", "-y", "-i", video_path]

    if start_time > 0:
        cmd.extend(["-ss", str(start_time)])
    if end_time:
        cmd.extend(["-to", str(end_time)])

    cmd.extend([
        "-vf", f"fps={fps}",
        "-q:v", "2",  # High quality JPEG
        os.path.join(output_dir, "frame_%04d.jpg"),
    ])

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise VideoProcessorError(f"ffmpeg failed: {e.stderr}") from e

    # Get list of extracted frames
    frame_paths = sorted(Path(output_dir).glob("frame_*.jpg"))
    return len(frame_paths), [str(p) for p in frame_paths]


def extract_crop(frame: Any, bbox: Dict[str, Any]) -> Optional[Any]:
    """
    Extract a crop from a frame using bounding box.

    Args:
        frame: OpenCV image (numpy array)
        bbox: Bounding box dict with 'corners' or 'center'/'size'

    Returns:
        Cropped image or None if invalid
    """
    try:
        if "corners" in bbox:
            corners = bbox["corners"]
            x_coords = [c[0] for c in corners]
            y_coords = [c[1] for c in corners]
        elif "center" in bbox and "size" in bbox:
            cx, cy = bbox["center"]
            w, h = bbox["size"]
            x_coords = [cx - w / 2, cx + w / 2]
            y_coords = [cy - h / 2, cy + h / 2]
        else:
            return None

        x_min = max(0, int(min(x_coords)))
        y_min = max(0, int(min(y_coords)))
        x_max = min(frame.shape[1], int(max(x_coords)))
        y_max = min(frame.shape[0], int(max(y_coords)))

        if x_max <= x_min or y_max <= y_min:
            return None

        return frame[y_min:y_max, x_min:x_max]
    except Exception as e:
        LOGGER.warning(f"Failed to extract crop: {e}")
        return None


async def update_job_status(
    job_id: UUID,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    frames_extracted: Optional[int] = None,
    error_message: Optional[str] = None,
    metadata: Optional[VideoMetadata] = None,
) -> None:
    """Update video job status in database."""
    async with async_session() as session:
        result = await session.execute(
            select(VideoJob).where(VideoJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            return

        if status:
            job.status = status
            if status == "processing" and not job.started_at:
                job.started_at = datetime.utcnow()
            elif status in ("completed", "failed"):
                job.completed_at = datetime.utcnow()

        if progress is not None:
            job.progress_percent = progress
        if frames_extracted is not None:
            job.frames_extracted = frames_extracted
        if error_message:
            job.error_message = error_message

        if metadata:
            job.duration_seconds = metadata.duration_seconds
            job.fps = metadata.fps
            job.width = metadata.width
            job.height = metadata.height
            job.codec = metadata.codec

        await session.commit()


async def process_video_job(job_id: UUID, extraction_fps: float = 1.0) -> None:
    """
    Background task to process a video job.

    1. Extract metadata
    2. Extract frames
    3. Save frame records to DB
    """
    LOGGER.info(f"Processing video job {job_id}")

    try:
        # Get job from DB
        async with async_session() as session:
            result = await session.execute(
                select(VideoJob).where(VideoJob.id == job_id)
            )
            job = result.scalar_one_or_none()

            if not job:
                LOGGER.error(f"Job {job_id} not found")
                return

            video_path = job.stored_path

        # Update status to processing
        await update_job_status(job_id, status="processing")

        # Extract metadata
        LOGGER.info(f"Extracting metadata from {video_path}")
        metadata = get_video_metadata(video_path)
        await update_job_status(job_id, metadata=metadata)

        # Calculate expected frames
        expected_frames = int(metadata.duration_seconds * extraction_fps)
        LOGGER.info(f"Expecting ~{expected_frames} frames at {extraction_fps} fps")

        # Extract frames
        output_dir = str(Path(video_path).parent / "frames")
        frame_count, frame_paths = extract_frames(video_path, output_dir, fps=extraction_fps)
        LOGGER.info(f"Extracted {frame_count} frames to {output_dir}")

        # Save frame records to DB
        async with async_session() as session:
            for i, frame_path in enumerate(frame_paths):
                # Get frame dimensions
                img = cv2.imread(frame_path)
                height, width = img.shape[:2] if img is not None else (None, None)

                frame = ExtractedFrame(
                    id=uuid4(),
                    job_id=job_id,
                    frame_index=i,
                    timestamp_ms=int(i * (1000 / extraction_fps)),
                    file_path=frame_path,
                    width=width,
                    height=height,
                )
                session.add(frame)

                # Update progress
                progress = int((i + 1) / frame_count * 100)
                if i % 10 == 0 or i == frame_count - 1:
                    await update_job_status(
                        job_id,
                        progress=progress,
                        frames_extracted=i + 1,
                    )

            await session.commit()

        # Mark complete
        await update_job_status(job_id, status="completed", progress=100)
        LOGGER.info(f"Job {job_id} completed: {frame_count} frames extracted")

    except Exception as e:
        LOGGER.exception(f"Job {job_id} failed: {e}")
        await update_job_status(job_id, status="failed", error_message=str(e))


def apply_consensus(
    state_history: List[str],
    current_smoothed: str,
    consensus_window: int = 5,
) -> str:
    """
    Apply N-frame consensus to determine smoothed state.

    Only switches state when the last N frames all predict the same state.

    Args:
        state_history: List of recent predicted states (newest last)
        current_smoothed: Current smoothed state
        consensus_window: Number of consecutive frames needed to switch

    Returns:
        New smoothed state
    """
    if len(state_history) < consensus_window:
        # Not enough history yet, keep current
        return current_smoothed

    # Check if last N frames all agree
    recent = state_history[-consensus_window:]
    if len(set(recent)) == 1:
        # All frames agree, switch to this state
        return recent[0]

    # No consensus, keep current smoothed state
    return current_smoothed


async def process_frames_with_classification(
    job_id: UUID,
    crop_json: Dict[str, Any],
    process_every_n: int = 1,
    update_db: bool = True,
    consensus_window: int = 5,
) -> Dict[str, Any]:
    """
    Process extracted frames with table classification.

    Args:
        job_id: Video job ID
        crop_json: Crop JSON with table bounding boxes
        process_every_n: Process every Nth frame
        update_db: Whether to update table states in DB
        consensus_window: Number of consecutive frames needed to switch state (default 5)

    Returns:
        Classification results summary
    """
    from app.ml.classifier_api import model_manager
    from app.services.table_state import update_table_state

    LOGGER.info(f"Processing frames for job {job_id}")

    # Check if model is loaded
    if not model_manager.is_loaded:
        raise VideoProcessorError("ML model not loaded. Start server with ML_ENABLED=true")

    # Get frames from DB
    async with async_session() as session:
        result = await session.execute(
            select(ExtractedFrame)
            .where(ExtractedFrame.job_id == job_id)
            .order_by(ExtractedFrame.frame_index)
        )
        frames = result.scalars().all()

    if not frames:
        raise VideoProcessorError("No frames found for job")

    tables = crop_json.get("tables", [])
    if not tables:
        raise VideoProcessorError("No tables in crop JSON")

    # Process frames
    results = {
        "frames_processed": 0,
        "tables_updated": 0,
        "consensus_window": consensus_window,
        "summary": {},
        "per_frame_results": [],
    }

    # Track state history and current smoothed state per table
    state_history: Dict[str, List[str]] = {}
    smoothed_states: Dict[str, str] = {}

    for table_info in tables:
        table_num = table_info.get("table_number", f"T{table_info.get('id', '?')}")
        results["summary"][table_num] = {
            "final_state": None,
            "final_smoothed_state": None,
            "state_changes": [],
            "smoothed_state_changes": [],
        }
        state_history[table_num] = []
        smoothed_states[table_num] = "unknown"

    for i, frame in enumerate(frames):
        if i % process_every_n != 0:
            continue

        # Load frame
        img = cv2.imread(frame.file_path)
        if img is None:
            LOGGER.warning(f"Failed to read frame {frame.file_path}")
            continue

        frame_results = {
            "frame_index": frame.frame_index,
            "timestamp_ms": frame.timestamp_ms,
            "tables": [],
        }

        for table_info in tables:
            table_id = table_info.get("table_id")
            table_num = table_info.get("table_number", f"T{table_info.get('id', '?')}")
            bbox = table_info.get("rotated_bbox", table_info.get("bbox"))

            if not bbox:
                continue

            # Extract crop
            crop = extract_crop(img, bbox)
            if crop is None:
                continue

            # Convert to PIL for classifier
            crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(crop_rgb)

            # Classify
            prediction = model_manager.predict(pil_image)
            state = prediction["label"]
            confidence = prediction["confidence"]

            # Apply N-frame consensus for temporal smoothing
            state_history[table_num].append(state)
            prev_smoothed = smoothed_states[table_num]
            smoothed_state = apply_consensus(
                state_history[table_num],
                prev_smoothed,
                consensus_window,
            )
            smoothed_states[table_num] = smoothed_state

            # Store result
            table_result = {
                "table_id": table_id,
                "table_number": table_num,
                "state": state,
                "smoothed_state": smoothed_state,
                "confidence": confidence,
            }
            frame_results["tables"].append(table_result)

            # Track raw state changes
            summary = results["summary"][table_num]
            if not summary["state_changes"] or summary["state_changes"][-1]["state"] != state:
                summary["state_changes"].append({
                    "frame": frame.frame_index,
                    "state": state,
                    "confidence": confidence,
                })
            summary["final_state"] = state

            # Track smoothed state changes
            if not summary["smoothed_state_changes"] or summary["smoothed_state_changes"][-1]["state"] != smoothed_state:
                summary["smoothed_state_changes"].append({
                    "frame": frame.frame_index,
                    "state": smoothed_state,
                })
            summary["final_smoothed_state"] = smoothed_state

            # Save classification to DB
            async with async_session() as session:
                classification = FrameClassification(
                    id=uuid4(),
                    job_id=job_id,
                    frame_index=frame.frame_index,
                    table_id=UUID(table_id) if table_id else None,
                    table_number=table_num,
                    predicted_state=state,
                    confidence=confidence,
                    smoothed_state=smoothed_state,
                )
                session.add(classification)
                await session.commit()

            # Update table state in DB (use smoothed state for stability)
            if update_db and table_id and smoothed_state != "unknown" and smoothed_state != prev_smoothed:
                try:
                    async with async_session() as session:
                        await update_table_state(
                            session=session,
                            table_id=UUID(table_id),
                            new_state=smoothed_state,
                            confidence=confidence,
                            source="ml",
                        )
                        await session.commit()
                        results["tables_updated"] += 1
                except Exception as e:
                    LOGGER.warning(f"Failed to update table {table_id}: {e}")

        results["per_frame_results"].append(frame_results)
        results["frames_processed"] += 1

    LOGGER.info(
        f"Processed {results['frames_processed']} frames, "
        f"updated {results['tables_updated']} table states"
    )

    return results


def validate_video_file(filename: str, content_type: Optional[str], file_size: int) -> None:
    """
    Validate uploaded video file.

    Raises:
        VideoProcessorError: If validation fails
    """
    # Check extension
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise VideoProcessorError(
            f"Invalid file type: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Check content type
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise VideoProcessorError(
            f"Invalid content type: {content_type}"
        )

    # Check size
    if file_size > MAX_FILE_SIZE:
        raise VideoProcessorError(
            f"File too large: {file_size / 1024 / 1024:.1f}MB. Max: {MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
        )


async def save_uploaded_video(
    file_content: bytes,
    filename: str,
    job_id: UUID,
) -> str:
    """
    Save uploaded video to disk.

    Returns:
        Path to saved file
    """
    # Create job directory
    job_dir = Path(UPLOADS_DIR) / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._-")
    if not safe_name:
        safe_name = "video.mp4"

    file_path = job_dir / safe_name

    # Write file
    with open(file_path, "wb") as f:
        f.write(file_content)

    return str(file_path)
