#!/usr/bin/env python3
"""
Standalone SAM3 Video Classifier.

Classifies table states in a video using SAM3 segmentation with temporal smoothing.

LOGIC:
1. Run SAM3 ONCE per frame to detect all "person" masks
2. Run SAM3 ONCE per frame to detect all "plate" masks
3. For each table bounding box:
   - Compute intersection of bbox with person masks
   - If person intersection > 15% of bbox area → OCCUPIED
   - Else if plate intersection > 1% of bbox area → DIRTY
   - Else → CLEAN
4. Apply temporal smoothing (N-frame consensus)

Usage:
    python classify_video.py --video /path/to/video.mp4 --crop-json /path/to/crop.json

Output:
    - Annotated visualization video with bounding boxes and states
    - JSON file with all classification results

python classify_videos.py --crop-json "./demovids/3_1_Mimosas/annotations.json" --video "./demovids/3_1_Mimosas/raw1.mp4" --output "./demovids/3_1_Mimosas/demo1.mp4" --output-json "./demovids//3_1_Mimosas/results.json1"
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch
from PIL import Image

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
LOGGER = logging.getLogger(__name__)

# Detection thresholds
PERSON_THRESHOLD = 0.5
PLATE_THRESHOLD = 0.4
PERSON_AREA_THRESHOLD = 0.15  # Person must cover >15% of bbox to be "occupied"
PLATE_AREA_THRESHOLD = 0.005  # Plate must cover >0.5% of bbox to be "dirty"

# Color scheme (BGR format for OpenCV) - matches pipeline
STATE_COLORS = {
    "clean": (0, 200, 0),       # Green
    "occupied": (0, 200, 255),  # Yellow/Orange
    "dirty": (0, 0, 200),       # Red
    "unknown": (128, 128, 128), # Gray
}

FILL_OPACITY = 0.3  # 30% opacity for box fill
MASK_OPACITY = 0.4  # 40% opacity for mask overlay

# Mask colors (BGR)
PERSON_MASK_COLOR = (255, 100, 100)  # Light blue for person masks
PLATE_MASK_COLOR = (100, 100, 255)   # Light red for plate masks


class SAM3Detector:
    """SAM3-based object detector - runs once per frame."""

    def __init__(self, device: str = None):
        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        self.device = device
        self._model = None
        self._processor = None
        LOGGER.info(f"SAM3Detector initialized (device: {device})")

    def _load_model(self) -> None:
        if self._model is not None:
            return

        from transformers import Sam3Model, Sam3Processor

        LOGGER.info("Loading SAM3 model (facebook/sam3)...")
        self._processor = Sam3Processor.from_pretrained("facebook/sam3")
        self._model = Sam3Model.from_pretrained("facebook/sam3")

        if self.device == "cuda":
            self._model = self._model.to(self.device, dtype=torch.bfloat16)
        else:
            self._model = self._model.to(self.device)

        self._model.eval()
        LOGGER.info(f"SAM3 model loaded on {self.device}")

    @torch.no_grad()
    def detect(
        self,
        image: Image.Image,
        prompt: str,
        threshold: float = 0.5,
    ) -> List[np.ndarray]:
        """
        Run SAM3 detection for a specific prompt on full frame.

        Returns list of binary masks (numpy arrays, same size as image).
        """
        self._load_model()

        if image.mode != "RGB":
            image = image.convert("RGB")

        inputs = self._processor(
            images=image,
            text=prompt,
            return_tensors="pt"
        ).to(self.device)

        outputs = self._model(**inputs)

        results = self._processor.post_process_instance_segmentation(
            outputs,
            threshold=threshold,
            mask_threshold=0.5,
            target_sizes=inputs.get("original_sizes").tolist()
        )[0]

        masks = results.get("masks", [])
        mask_arrays = []

        if masks is not None and len(masks) > 0:
            for mask in masks:
                if torch.is_tensor(mask):
                    mask_np = mask.cpu().numpy().astype(bool)
                else:
                    mask_np = np.array(mask).astype(bool)
                mask_arrays.append(mask_np)

        return mask_arrays


def create_bbox_mask(bbox: Dict[str, Any], frame_height: int, frame_width: int) -> np.ndarray:
    """
    Create a binary mask for a bounding box (polygon or rectangle).

    Returns a boolean numpy array of shape (frame_height, frame_width).
    """
    mask = np.zeros((frame_height, frame_width), dtype=np.uint8)

    if "corners" in bbox:
        corners = bbox["corners"]
        pts = np.array(corners, dtype=np.int32)
        cv2.fillPoly(mask, [pts], 1)
    elif "center" in bbox and "size" in bbox:
        cx, cy = bbox["center"]
        w, h = bbox["size"]
        x1 = max(0, int(cx - w / 2))
        y1 = max(0, int(cy - h / 2))
        x2 = min(frame_width, int(cx + w / 2))
        y2 = min(frame_height, int(cy + h / 2))
        mask[y1:y2, x1:x2] = 1

    return mask.astype(bool)


def compute_mask_intersection(mask1: np.ndarray, mask2: np.ndarray) -> int:
    """Compute the number of pixels where both masks are True."""
    return int(np.logical_and(mask1, mask2).sum())


def classify_tables_from_masks(
    tables: List[Dict[str, Any]],
    person_masks: List[np.ndarray],
    plate_masks: List[np.ndarray],
    frame_height: int,
    frame_width: int,
) -> Dict[str, Dict[str, Any]]:
    """
    Classify each table based on intersection with detected masks.

    Logic for each table:
    1. Create bbox mask
    2. Compute person intersection ratio
    3. If person_ratio > 15% → occupied
    4. Else compute plate intersection ratio
    5. If plate_ratio > 3% → dirty
    6. Else → clean
    """
    results = {}

    # Combine all person masks into one (union)
    if person_masks:
        combined_person_mask = np.zeros((frame_height, frame_width), dtype=bool)
        for pm in person_masks:
            combined_person_mask = np.logical_or(combined_person_mask, pm)
    else:
        combined_person_mask = None

    # Combine all plate masks into one (union)
    if plate_masks:
        combined_plate_mask = np.zeros((frame_height, frame_width), dtype=bool)
        for pm in plate_masks:
            combined_plate_mask = np.logical_or(combined_plate_mask, pm)
    else:
        combined_plate_mask = None

    for table_info in tables:
        table_num = f"T{table_info.get('id', '?')}"
        bbox = table_info.get("rotated_bbox", table_info.get("bbox"))

        if not bbox:
            results[table_num] = {"state": "unknown", "confidence": 0.0, "details": {}}
            continue

        bbox_mask = create_bbox_mask(bbox, frame_height, frame_width)
        bbox_area = int(bbox_mask.sum())

        if bbox_area == 0:
            results[table_num] = {"state": "unknown", "confidence": 0.0, "details": {}}
            continue

        # Check person intersection
        if combined_person_mask is not None:
            person_intersection = compute_mask_intersection(bbox_mask, combined_person_mask)
            person_ratio = person_intersection / bbox_area
        else:
            person_intersection = 0
            person_ratio = 0.0

        # Classification logic
        if person_ratio >= PERSON_AREA_THRESHOLD:
            # Person covers >15% of bbox → occupied
            confidence = min(0.99, 0.5 + person_ratio)
            results[table_num] = {
                "state": "occupied",
                "confidence": round(confidence, 4),
                "details": {
                    "person_intersection_pixels": person_intersection,
                    "bbox_area": bbox_area,
                    "person_ratio": round(person_ratio, 4),
                },
            }
        else:
            # Check plate intersection
            if combined_plate_mask is not None:
                plate_intersection = compute_mask_intersection(bbox_mask, combined_plate_mask)
                plate_ratio = plate_intersection / bbox_area
            else:
                plate_intersection = 0
                plate_ratio = 0.0

            if plate_ratio >= PLATE_AREA_THRESHOLD:
                # Plates cover >3% of bbox → dirty
                confidence = min(0.95, 0.5 + plate_ratio * 2)
                results[table_num] = {
                    "state": "dirty",
                    "confidence": round(confidence, 4),
                    "details": {
                        "plate_intersection_pixels": plate_intersection,
                        "bbox_area": bbox_area,
                        "plate_ratio": round(plate_ratio, 4),
                    },
                }
            else:
                # Nothing significant detected → clean
                if person_ratio > 0:
                    confidence = 0.7
                    details = {"person_detected_but_small": True, "person_ratio": round(person_ratio, 4)}
                else:
                    confidence = 0.9
                    details = {}

                results[table_num] = {
                    "state": "clean",
                    "confidence": round(confidence, 4),
                    "details": details,
                }

    return results


def get_video_metadata(video_path: str) -> Dict[str, Any]:
    """Extract video metadata using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    video_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if not video_stream:
        raise ValueError("No video stream found")

    fps_str = video_stream.get("r_frame_rate", "30/1")
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    else:
        fps = float(fps_str)

    duration = float(data.get("format", {}).get("duration", 0))
    if duration == 0:
        duration = float(video_stream.get("duration", 0))

    return {
        "duration": duration,
        "fps": fps,
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
    }


def extract_frames_at_fps(video_path: str, output_dir: str, fps: float = 1.0) -> List[str]:
    """Extract frames at specified FPS."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"fps={fps}",
        "-q:v", "2",
        os.path.join(output_dir, "frame_%05d.jpg"),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    frame_paths = sorted(Path(output_dir).glob("frame_*.jpg"))
    return [str(p) for p in frame_paths]


def apply_consensus(state_history: List[str], current_smoothed: str, window: int = 5) -> str:
    """Apply N-frame consensus for temporal smoothing."""
    if len(state_history) < window:
        return current_smoothed
    recent = state_history[-window:]
    if len(set(recent)) == 1:
        return recent[0]
    return current_smoothed


def draw_rotated_box(
    frame: np.ndarray,
    corners: List[List[float]],
    color: Tuple[int, int, int],
    label: str,
    fill_opacity: float = FILL_OPACITY,
) -> np.ndarray:
    """
    Draw a rotated bounding box with semi-transparent fill and label.
    Matches the pipeline's visualization style.
    """
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


def draw_masks_on_frame(
    frame: np.ndarray,
    person_mask: Optional[np.ndarray],
    plate_mask: Optional[np.ndarray],
    opacity: float = MASK_OPACITY,
) -> np.ndarray:
    """
    Draw person and plate masks on frame with semi-transparent overlay.
    """
    overlay = frame.copy()

    if person_mask is not None and person_mask.any():
        # Draw person mask in light blue
        overlay[person_mask] = PERSON_MASK_COLOR

    if plate_mask is not None and plate_mask.any():
        # Draw plate mask in light red
        overlay[plate_mask] = PLATE_MASK_COLOR

    # Blend overlay with original
    frame = cv2.addWeighted(overlay, opacity, frame, 1 - opacity, 0)
    return frame


def get_bbox_corners(bbox: Dict[str, Any]) -> Optional[List[List[float]]]:
    """Extract corners from bbox dict."""
    if "corners" in bbox:
        return bbox["corners"]
    elif "center" in bbox and "size" in bbox:
        cx, cy = bbox["center"]
        w, h = bbox["size"]
        return [
            [cx - w/2, cy - h/2],
            [cx + w/2, cy - h/2],
            [cx + w/2, cy + h/2],
            [cx - w/2, cy + h/2],
        ]
    return None


def create_visualization_video(
    frame_paths: List[str],
    output_path: str,
    tables: List[Dict[str, Any]],
    frame_results: List[Dict[str, Any]],
    frame_masks: List[Dict[str, Optional[np.ndarray]]],
    output_fps: float = 1.0,
) -> None:
    """
    Create visualization video from processed frames only.
    Includes mask overlays for persons (blue) and plates (red).
    """
    LOGGER.info(f"Creating visualization video: {output_path}")

    if not frame_paths:
        LOGGER.error("No frames to visualize")
        return

    # Get dimensions from first frame
    first_frame = cv2.imread(frame_paths[0])
    if first_frame is None:
        LOGGER.error(f"Could not read first frame: {frame_paths[0]}")
        return

    height, width = first_frame.shape[:2]

    # Build table bbox lookup
    table_bboxes: Dict[str, List[List[float]]] = {}
    for table in tables:
        table_num = f"T{table.get('id', '?')}"
        bbox = table.get("rotated_bbox", table.get("bbox"))
        if bbox:
            corners = get_bbox_corners(bbox)
            if corners:
                table_bboxes[table_num] = corners

    # Build results lookup by frame index
    results_by_frame = {fr["frame_index"]: fr for fr in frame_results}

    # Initialize video writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(output_path, fourcc, output_fps, (width, height))

    if not writer.isOpened():
        LOGGER.error(f"Could not create video writer for {output_path}")
        return

    LOGGER.info(f"Writing annotated video: {width}x{height} @ {output_fps} fps, {len(frame_paths)} frames")

    # Process each extracted frame
    for i, frame_path in enumerate(frame_paths):
        frame = cv2.imread(frame_path)
        if frame is None:
            LOGGER.warning(f"Could not read frame: {frame_path}")
            continue

        # Draw masks first (underneath bboxes)
        if i < len(frame_masks):
            masks = frame_masks[i]
            frame = draw_masks_on_frame(
                frame,
                masks.get("person_mask"),
                masks.get("plate_mask"),
            )

        # Get classifications for this frame
        frame_result = results_by_frame.get(i, {})
        table_states = {t["table_number"]: t for t in frame_result.get("tables", [])}

        # Draw each table's bounding box
        for table_num, corners in table_bboxes.items():
            if table_num in table_states:
                t = table_states[table_num]
                raw_state = t["raw_state"]
                smoothed_state = t["smoothed_state"]
                confidence = t["confidence"]

                # Use smoothed state for color
                state = smoothed_state
                color = STATE_COLORS.get(state, STATE_COLORS["unknown"])

                # Show both smoothed and raw if different
                if state != raw_state:
                    label = f"{table_num}: {state} (raw:{raw_state[:3]})"
                else:
                    label = f"{table_num}: {state} ({confidence:.0%})"
            else:
                state = "unknown"
                color = STATE_COLORS["unknown"]
                label = f"{table_num}: ?"

            frame = draw_rotated_box(frame, corners, color, label)

        # Add timestamp info and legend
        timestamp = i / output_fps if output_fps > 0 else i
        info_text = f"Frame {i} | Time: {timestamp:.1f}s"
        cv2.putText(frame, info_text, (10, height - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Add mask legend
        cv2.putText(frame, "Blue=Person", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, PERSON_MASK_COLOR, 1)
        cv2.putText(frame, "Red=Plate", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, PLATE_MASK_COLOR, 1)

        writer.write(frame)

    writer.release()
    LOGGER.info(f"Visualization saved to {output_path} ({len(frame_paths)} frames)")


def main():
    parser = argparse.ArgumentParser(
        description="Classify table states in video using SAM3 (single inference per frame)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
CLASSIFICATION LOGIC:
  1. Run SAM3 ONCE per frame to detect all "person" masks
  2. Run SAM3 ONCE per frame to detect all "plate" masks
  3. For each table bounding box:
     - Compute intersection with person masks
     - If person pixels > 15% of bbox → OCCUPIED
     - Else if plate pixels > 1% of bbox → DIRTY
     - Else → CLEAN
  4. Apply N-frame temporal smoothing (consensus window)

Examples:
  python classify_video.py --video demo.mp4 --crop-json crops.json
  python classify_video.py --video demo.mp4 --crop-json crops.json --output result.mp4 --consensus 3
        """,
    )
    parser.add_argument("--video", "-v", required=True, help="Path to input video file")
    parser.add_argument("--crop-json", "-c", required=True, help="Path to crop JSON file")
    parser.add_argument("--output", "-o", help="Output video path (default: <video>_classified.mp4)")
    parser.add_argument("--output-json", help="Output JSON path (default: <video>_results.json)")
    parser.add_argument("--fps", type=float, default=1.0, help="Frames per second to process (default: 1)")
    parser.add_argument("--consensus", type=int, default=2, help="Consensus window for smoothing (default: 2)")
    parser.add_argument("--device", choices=["cuda", "mps", "cpu"], help="Device to use (auto-detect if not set)")
    args = parser.parse_args()

    # Validate inputs
    if not os.path.exists(args.video):
        LOGGER.error(f"Video file not found: {args.video}")
        sys.exit(1)
    if not os.path.exists(args.crop_json):
        LOGGER.error(f"Crop JSON file not found: {args.crop_json}")
        sys.exit(1)

    # Set output paths
    video_stem = Path(args.video).stem
    output_video = args.output or f"{video_stem}_classified.mp4"
    output_json = args.output_json or f"{video_stem}_results.json"

    # Load crop JSON
    with open(args.crop_json) as f:
        crop_json = json.load(f)

    if "crop_json" in crop_json:
        crop_json = crop_json["crop_json"]

    tables = crop_json.get("tables", [])
    LOGGER.info(f"Loaded {len(tables)} tables from crop JSON")

    # Get video metadata
    metadata = get_video_metadata(args.video)
    frame_height = metadata["height"]
    frame_width = metadata["width"]
    LOGGER.info(f"Video: {frame_width}x{frame_height}, {metadata['fps']:.1f}fps, {metadata['duration']:.1f}s")

    # Extract frames
    with tempfile.TemporaryDirectory() as temp_dir:
        LOGGER.info(f"Extracting frames at {args.fps} fps...")
        frame_paths = extract_frames_at_fps(args.video, temp_dir, fps=args.fps)
        LOGGER.info(f"Extracted {len(frame_paths)} frames")

        # Initialize detector
        detector = SAM3Detector(device=args.device)

        # Track state history for temporal smoothing
        state_history: Dict[str, List[str]] = defaultdict(list)
        smoothed_states: Dict[str, str] = defaultdict(lambda: "unknown")

        # Process frames
        frame_results = []
        frame_masks = []  # Store masks for visualization
        total_frames = len(frame_paths)

        for i, frame_path in enumerate(frame_paths):
            LOGGER.info(f"Processing frame {i + 1}/{total_frames}...")

            # Load frame as PIL
            pil_image = Image.open(frame_path)
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")

            # Run SAM3 ONCE for "person" on full frame
            LOGGER.info(f"  Detecting persons...")
            person_masks = detector.detect(pil_image, "person", PERSON_THRESHOLD)
            LOGGER.info(f"  Found {len(person_masks)} person mask(s)")

            # Run SAM3 ONCE for "plate" on full frame
            LOGGER.info(f"  Detecting plates...")
            plate_masks = detector.detect(pil_image, "plate", PLATE_THRESHOLD)
            LOGGER.info(f"  Found {len(plate_masks)} plate mask(s)")

            # Combine masks for visualization
            combined_person = None
            if person_masks:
                combined_person = np.zeros((frame_height, frame_width), dtype=bool)
                for pm in person_masks:
                    combined_person = np.logical_or(combined_person, pm)

            combined_plate = None
            if plate_masks:
                combined_plate = np.zeros((frame_height, frame_width), dtype=bool)
                for pm in plate_masks:
                    combined_plate = np.logical_or(combined_plate, pm)

            frame_masks.append({
                "person_mask": combined_person,
                "plate_mask": combined_plate,
            })

            # Classify each table by mask intersection
            table_classifications = classify_tables_from_masks(
                tables, person_masks, plate_masks, frame_height, frame_width
            )

            frame_result = {
                "frame_index": i,
                "timestamp_s": i / args.fps,
                "person_masks_detected": len(person_masks),
                "plate_masks_detected": len(plate_masks),
                "tables": [],
            }

            for table_info in tables:
                table_num = f"T{table_info.get('id', '?')}"

                if table_num in table_classifications:
                    classification = table_classifications[table_num]
                    state = classification["state"]
                    confidence = classification["confidence"]
                    details = classification["details"]
                else:
                    state = "unknown"
                    confidence = 0.0
                    details = {}

                # Apply temporal smoothing
                state_history[table_num].append(state)
                prev_smoothed = smoothed_states[table_num]
                smoothed_state = apply_consensus(state_history[table_num], prev_smoothed, args.consensus)
                smoothed_states[table_num] = smoothed_state

                frame_result["tables"].append({
                    "table_number": table_num,
                    "raw_state": state,
                    "smoothed_state": smoothed_state,
                    "confidence": confidence,
                    "details": details,
                })

            frame_results.append(frame_result)

        # Save results JSON
        results_data = {
            "video": args.video,
            "crop_json": args.crop_json,
            "settings": {
                "fps": args.fps,
                "consensus_window": args.consensus,
                "person_threshold": PERSON_THRESHOLD,
                "plate_threshold": PLATE_THRESHOLD,
                "person_area_threshold": PERSON_AREA_THRESHOLD,
                "plate_area_threshold": PLATE_AREA_THRESHOLD,
            },
            "metadata": metadata,
            "frames_processed": len(frame_results),
            "frame_results": frame_results,
            "final_states": {
                table_num: smoothed_states[table_num]
                for table_num in sorted(smoothed_states.keys())
            },
        }

        with open(output_json, "w") as f:
            json.dump(results_data, f, indent=2)
        LOGGER.info(f"Results saved to {output_json}")

        # Create visualization video (only from processed frames, with masks)
        create_visualization_video(
            frame_paths,
            output_video,
            tables,
            frame_results,
            frame_masks,
            output_fps=args.fps,
        )

    # Print summary
    LOGGER.info("\n" + "=" * 60)
    LOGGER.info("CLASSIFICATION SUMMARY")
    LOGGER.info("=" * 60)
    for table_num in sorted(smoothed_states.keys()):
        state = smoothed_states[table_num]
        history = state_history[table_num]
        state_counts = defaultdict(int)
        for s in history:
            state_counts[s] += 1
        counts_str = ", ".join(f"{s}: {c}" for s, c in sorted(state_counts.items()))
        LOGGER.info(f"  {table_num}: {state.upper():10s} ({counts_str})")
    LOGGER.info("=" * 60)
    LOGGER.info(f"Output video: {output_video}")
    LOGGER.info(f"Output JSON: {output_json}")


if __name__ == "__main__":
    main()
