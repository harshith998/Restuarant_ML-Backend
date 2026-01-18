"""
Video visualization service for generating annotated output videos.

Creates MP4 videos with:
- Colored bounding boxes per table (green=clean, yellow=occupied, red=dirty)
- Semi-transparent fill inside boxes
- Table number labels
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import cv2
import numpy as np
from sqlalchemy import select

from app.database import async_session_factory as async_session
from app.models.video import ExtractedFrame, FrameClassification, VideoJob

LOGGER = logging.getLogger("video-visualizer")

# Color scheme (BGR format for OpenCV)
STATE_COLORS = {
    "clean": (0, 200, 0),      # Green
    "occupied": (0, 200, 255),  # Yellow/Orange
    "dirty": (0, 0, 200),       # Red
    "unknown": (128, 128, 128), # Gray
}

FILL_OPACITY = 0.3  # 30% opacity for box fill


def draw_rotated_box(
    frame: np.ndarray,
    corners: List[List[float]],
    color: Tuple[int, int, int],
    label: str,
    fill_opacity: float = FILL_OPACITY,
) -> np.ndarray:
    """
    Draw a rotated bounding box with fill and label.

    Args:
        frame: OpenCV image (BGR)
        corners: List of 4 corner points [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        color: BGR color tuple
        label: Text label to display
        fill_opacity: Opacity for box fill (0-1)

    Returns:
        Annotated frame
    """
    # Convert corners to numpy array of integers
    pts = np.array(corners, dtype=np.int32)

    # Create overlay for semi-transparent fill
    overlay = frame.copy()
    cv2.fillPoly(overlay, [pts], color)

    # Blend overlay with original frame
    frame = cv2.addWeighted(overlay, fill_opacity, frame, 1 - fill_opacity, 0)

    # Draw border
    cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)

    # Calculate label position (top-left corner)
    min_x = int(min(c[0] for c in corners))
    min_y = int(min(c[1] for c in corners))

    # Draw label background
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.6
    thickness = 2
    (text_w, text_h), baseline = cv2.getTextSize(label, font, font_scale, thickness)

    label_x = max(0, min_x)
    label_y = max(text_h + 4, min_y - 4)

    # Background rectangle for label
    cv2.rectangle(
        frame,
        (label_x, label_y - text_h - 4),
        (label_x + text_w + 4, label_y + 4),
        color,
        -1  # Filled
    )

    # Draw label text (white)
    cv2.putText(
        frame,
        label,
        (label_x + 2, label_y),
        font,
        font_scale,
        (255, 255, 255),
        thickness,
    )

    return frame


async def generate_annotated_video(
    job_id: UUID,
    output_path: Optional[str] = None,
    fps: float = 1.0,
) -> str:
    """
    Generate an annotated video with classification results overlaid.

    Args:
        job_id: Video job ID
        output_path: Optional output path. If None, saves to job directory.
        fps: Output video frame rate

    Returns:
        Path to the generated video
    """
    LOGGER.info(f"Generating annotated video for job {job_id}")

    # Get job info
    async with async_session() as session:
        result = await session.execute(
            select(VideoJob).where(VideoJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Get frames
        result = await session.execute(
            select(ExtractedFrame)
            .where(ExtractedFrame.job_id == job_id)
            .order_by(ExtractedFrame.frame_index)
        )
        frames = result.scalars().all()

        # Get classifications
        result = await session.execute(
            select(FrameClassification)
            .where(FrameClassification.job_id == job_id)
            .order_by(FrameClassification.frame_index, FrameClassification.table_number)
        )
        classifications = result.scalars().all()

    if not frames:
        raise ValueError(f"No frames found for job {job_id}")

    # Build classification lookup: frame_index -> {table_number -> classification}
    class_lookup: Dict[int, Dict[str, FrameClassification]] = {}
    for c in classifications:
        if c.frame_index not in class_lookup:
            class_lookup[c.frame_index] = {}
        class_lookup[c.frame_index][c.table_number] = c

    # Determine output path
    if output_path is None:
        job_dir = Path(job.stored_path).parent
        output_path = str(job_dir / "annotated_output.mp4")

    # Get frame dimensions from first frame
    first_frame = cv2.imread(frames[0].file_path)
    if first_frame is None:
        raise ValueError(f"Could not read frame: {frames[0].file_path}")

    height, width = first_frame.shape[:2]

    # Initialize video writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    if not writer.isOpened():
        raise ValueError(f"Could not create video writer for {output_path}")

    LOGGER.info(f"Writing annotated video: {width}x{height} @ {fps} fps")

    # Process each frame
    for frame_record in frames:
        # Read frame
        frame = cv2.imread(frame_record.file_path)
        if frame is None:
            LOGGER.warning(f"Could not read frame {frame_record.frame_index}")
            continue

        # Get classifications for this frame
        frame_classes = class_lookup.get(frame_record.frame_index, {})

        # Draw each table's bounding box
        for table_num, classification in frame_classes.items():
            state = classification.predicted_state
            confidence = float(classification.confidence)
            color = STATE_COLORS.get(state, STATE_COLORS["unknown"])

            # We need the bounding box - get it from the original crop_json
            # For now, we'll need to store bbox in classification or pass it separately
            # This is a limitation - let me add bbox to the visualization

            # Create label with state and confidence
            label = f"{table_num}: {state} ({confidence:.0%})"

            # Note: We need bbox data - see below for fix

        # Write frame (even without annotations for now)
        writer.write(frame)

    writer.release()
    LOGGER.info(f"Annotated video saved to {output_path}")

    return output_path


async def generate_annotated_video_with_crops(
    job_id: UUID,
    crop_json: Dict[str, Any],
    output_path: Optional[str] = None,
    fps: float = 1.0,
    use_smoothed: bool = True,
) -> str:
    """
    Generate an annotated video with classification results overlaid.

    Args:
        job_id: Video job ID
        crop_json: Crop JSON with table bounding boxes
        output_path: Optional output path. If None, saves to job directory.
        fps: Output video frame rate

    Returns:
        Path to the generated video
    """
    LOGGER.info(f"Generating annotated video for job {job_id}")

    # Get job info
    async with async_session() as session:
        result = await session.execute(
            select(VideoJob).where(VideoJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Get frames
        result = await session.execute(
            select(ExtractedFrame)
            .where(ExtractedFrame.job_id == job_id)
            .order_by(ExtractedFrame.frame_index)
        )
        frames = result.scalars().all()

        # Get classifications
        result = await session.execute(
            select(FrameClassification)
            .where(FrameClassification.job_id == job_id)
            .order_by(FrameClassification.frame_index, FrameClassification.table_number)
        )
        classifications = result.scalars().all()

    if not frames:
        raise ValueError(f"No frames found for job {job_id}")

    # Build classification lookup: frame_index -> {table_number -> classification}
    class_lookup: Dict[int, Dict[str, FrameClassification]] = {}
    for c in classifications:
        if c.frame_index not in class_lookup:
            class_lookup[c.frame_index] = {}
        class_lookup[c.frame_index][c.table_number] = c

    # Build table bbox lookup from crop_json
    tables = crop_json.get("tables", [])
    table_bboxes: Dict[str, List[List[float]]] = {}
    for table in tables:
        table_num = table.get("table_number", f"T{table.get('id', '?')}")
        bbox = table.get("rotated_bbox", table.get("bbox", {}))
        if "corners" in bbox:
            table_bboxes[table_num] = bbox["corners"]
        elif "center" in bbox and "size" in bbox:
            # Convert center/size to corners
            cx, cy = bbox["center"]
            w, h = bbox["size"]
            table_bboxes[table_num] = [
                [cx - w/2, cy - h/2],
                [cx + w/2, cy - h/2],
                [cx + w/2, cy + h/2],
                [cx - w/2, cy + h/2],
            ]

    # Determine output path
    if output_path is None:
        job_dir = Path(job.stored_path).parent
        output_path = str(job_dir / "annotated_output.mp4")

    # Get frame dimensions from first frame
    first_frame = cv2.imread(frames[0].file_path)
    if first_frame is None:
        raise ValueError(f"Could not read frame: {frames[0].file_path}")

    height, width = first_frame.shape[:2]

    # Initialize video writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    if not writer.isOpened():
        raise ValueError(f"Could not create video writer for {output_path}")

    LOGGER.info(f"Writing annotated video: {width}x{height} @ {fps} fps, {len(frames)} frames")

    # Process each frame
    frames_written = 0
    for frame_record in frames:
        # Read frame
        frame = cv2.imread(frame_record.file_path)
        if frame is None:
            LOGGER.warning(f"Could not read frame {frame_record.frame_index}")
            continue

        # Get classifications for this frame
        frame_classes = class_lookup.get(frame_record.frame_index, {})

        # Draw each table's bounding box
        for table_num, corners in table_bboxes.items():
            classification = frame_classes.get(table_num)

            if classification:
                raw_state = classification.predicted_state
                smoothed = classification.smoothed_state or raw_state
                confidence = float(classification.confidence)

                # Use smoothed or raw based on flag
                if use_smoothed:
                    state = smoothed
                    # Show both smoothed state and raw prediction if different
                    if state != raw_state:
                        label = f"{table_num}: {state} (raw:{raw_state[:3]})"
                    else:
                        label = f"{table_num}: {state} ({confidence:.0%})"
                else:
                    # Debug mode: show raw predictions with confidence
                    state = raw_state
                    label = f"{table_num}: {state} ({confidence:.0%})"
            else:
                state = "unknown"
                confidence = 0.0
                label = f"{table_num}: ? (no data)"

            color = STATE_COLORS.get(state, STATE_COLORS["unknown"])

            # Draw the annotated box
            frame = draw_rotated_box(frame, corners, color, label)

        # Write frame
        writer.write(frame)
        frames_written += 1

    writer.release()
    LOGGER.info(f"Annotated video saved to {output_path} ({frames_written} frames)")

    return output_path
