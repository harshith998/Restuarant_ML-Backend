#!/usr/bin/env python3
"""
Live SAM3 Classification Viewer.

Captures a specific application window, sends frames to RunPod GPU,
displays annotated frames in a live viewer.

Usage:
    python live_classifier.py --app "Swann" --crop-json annotations.json

Requirements:
    pip install pyobjc-framework-Quartz opencv-python requests numpy pillow
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import time
from typing import Optional, Tuple

import cv2
import numpy as np
import requests
from PIL import Image

# macOS window capture
import Quartz
from Quartz import (
    CGWindowListCopyWindowInfo,
    CGWindowListCreateImage,
    kCGNullWindowID,
    kCGWindowImageDefault,
    kCGWindowListOptionIncludingWindow,
    kCGWindowListOptionAll,
)
import Quartz.CoreGraphics as CG

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)

# RunPod endpoint
DEFAULT_ENDPOINT = "https://11qbv1ws84wpwm-8888.proxy.runpod.net/classify"


def list_windows() -> list[dict]:
    """List all windows with their IDs and owner names."""
    window_list = CGWindowListCopyWindowInfo(
        kCGWindowListOptionAll, kCGNullWindowID
    )
    windows = []
    for window in window_list:
        owner = window.get("kCGWindowOwnerName", "")
        name = window.get("kCGWindowName", "")
        window_id = window.get("kCGWindowNumber", 0)
        layer = window.get("kCGWindowLayer", 0)
        bounds = window.get("kCGWindowBounds", {})
        width = bounds.get("Width", 0)
        height = bounds.get("Height", 0)

        # Skip tiny windows and menu bar items
        if width > 100 and height > 100:
            windows.append({
                "id": window_id,
                "owner": owner,
                "name": name,
                "layer": layer,
                "width": width,
                "height": height,
            })
    return windows


def find_window_by_app(app_name: str) -> Optional[int]:
    """Find window ID by application name (partial match)."""
    windows = list_windows()
    app_lower = app_name.lower()

    # First try exact owner match
    for w in windows:
        if app_lower in w["owner"].lower():
            LOGGER.info(f"Found window: {w['owner']} - {w['name']} ({w['width']}x{w['height']})")
            return w["id"]

    # Then try window name match
    for w in windows:
        if app_lower in w["name"].lower():
            LOGGER.info(f"Found window: {w['owner']} - {w['name']} ({w['width']}x{w['height']})")
            return w["id"]

    return None


def capture_window(window_id: int) -> Optional[np.ndarray]:
    """Capture a specific window by ID, returns BGR numpy array."""
    # Capture the window
    cg_image = CGWindowListCreateImage(
        CG.CGRectNull,  # Capture full window bounds
        kCGWindowListOptionIncludingWindow,
        window_id,
        kCGWindowImageDefault
    )

    if cg_image is None:
        return None

    # Get image dimensions
    width = CG.CGImageGetWidth(cg_image)
    height = CG.CGImageGetHeight(cg_image)

    if width == 0 or height == 0:
        return None

    # Create bitmap context and draw image
    bytes_per_row = CG.CGImageGetBytesPerRow(cg_image)

    # Get pixel data
    data_provider = CG.CGImageGetDataProvider(cg_image)
    data = CG.CGDataProviderCopyData(data_provider)

    # Convert to numpy array (BGRA format on macOS)
    arr = np.frombuffer(data, dtype=np.uint8)
    arr = arr.reshape((height, bytes_per_row // 4, 4))
    arr = arr[:, :width, :]  # Trim padding

    # Convert BGRA to BGR
    bgr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)

    return bgr


def scale_crop_json(crop_json: dict, target_width: int, target_height: int) -> dict:
    """
    Scale bounding boxes from original resolution to target resolution.

    Preserves aspect ratio - scales based on the original frame dimensions
    stored in crop_json (frame_width, frame_height).
    """
    orig_width = crop_json.get("frame_width", target_width)
    orig_height = crop_json.get("frame_height", target_height)

    # Calculate scale factors
    scale_x = target_width / orig_width
    scale_y = target_height / orig_height

    # If no scaling needed, return as-is
    if abs(scale_x - 1.0) < 0.01 and abs(scale_y - 1.0) < 0.01:
        return crop_json

    # Deep copy and scale
    scaled = {
        "video_name": crop_json.get("video_name", "live"),
        "frame_index": crop_json.get("frame_index", 0),
        "frame_width": target_width,
        "frame_height": target_height,
        "tables": [],
    }

    for table in crop_json.get("tables", []):
        scaled_table = {
            "id": table.get("id"),
            "saved": table.get("saved", False),
        }

        # Scale rotated_bbox if present
        if "rotated_bbox" in table:
            rb = table["rotated_bbox"]
            scaled_rb = {
                "angle": rb.get("angle", 0),
            }

            # Scale center
            if "center" in rb:
                scaled_rb["center"] = [
                    rb["center"][0] * scale_x,
                    rb["center"][1] * scale_y,
                ]

            # Scale size
            if "size" in rb:
                scaled_rb["size"] = [
                    rb["size"][0] * scale_x,
                    rb["size"][1] * scale_y,
                ]

            # Scale corners
            if "corners" in rb:
                scaled_rb["corners"] = [
                    [c[0] * scale_x, c[1] * scale_y]
                    for c in rb["corners"]
                ]

            scaled_table["rotated_bbox"] = scaled_rb

        # Scale regular bbox if present
        if "bbox" in table:
            bbox = table["bbox"]
            scaled_bbox = {}

            if "center" in bbox:
                scaled_bbox["center"] = [
                    bbox["center"][0] * scale_x,
                    bbox["center"][1] * scale_y,
                ]
            if "size" in bbox:
                scaled_bbox["size"] = [
                    bbox["size"][0] * scale_x,
                    bbox["size"][1] * scale_y,
                ]
            if "corners" in bbox:
                scaled_bbox["corners"] = [
                    [c[0] * scale_x, c[1] * scale_y]
                    for c in bbox["corners"]
                ]

            scaled_table["bbox"] = scaled_bbox

        scaled["tables"].append(scaled_table)

    return scaled


def send_to_server(
    frame: np.ndarray,
    crop_json: dict,
    endpoint: str,
    timeout: float = 30.0,
    jpeg_quality: int = 85,
) -> Tuple[Optional[np.ndarray], dict]:
    """
    Send frame to SAM3 server, return annotated frame.

    Resizes frame to match crop_json dimensions (frame_width, frame_height).

    Returns:
        Tuple of (annotated_frame, timing_dict)
    """
    timings = {}
    start = time.time()

    frame_height, frame_width = frame.shape[:2]

    # Resize to match crop_json dimensions
    target_width = crop_json.get("frame_width", frame_width)
    target_height = crop_json.get("frame_height", frame_height)

    if frame_width != target_width or frame_height != target_height:
        frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
        frame_width, frame_height = target_width, target_height

    timings["resize"] = time.time() - start

    # Encode frame as JPEG (lower quality for speed)
    encode_start = time.time()
    _, jpeg_bytes = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    timings["encode"] = time.time() - encode_start
    timings["size_kb"] = len(jpeg_bytes) / 1024

    # Prepare multipart form (no scaling needed - frame matches crop_json dimensions)
    files = {
        "image": ("frame.jpg", jpeg_bytes.tobytes(), "image/jpeg"),
    }
    data = {
        "crop_json": json.dumps(crop_json),
    }

    try:
        upload_start = time.time()
        response = requests.post(endpoint, files=files, data=data, timeout=timeout)
        timings["network"] = time.time() - upload_start
        timings["total"] = time.time() - start

        if response.status_code == 200:
            # Decode response JPEG
            decode_start = time.time()
            arr = np.frombuffer(response.content, dtype=np.uint8)
            annotated = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            timings["decode"] = time.time() - decode_start
            timings["response_kb"] = len(response.content) / 1024
            return annotated, timings
        else:
            LOGGER.warning(f"Server returned {response.status_code}: {response.text[:100]}")
            return None, timings

    except requests.exceptions.Timeout:
        timings["total"] = time.time() - start
        timings["error"] = "timeout"
        LOGGER.warning(f"Request timed out after {timings['total']:.1f}s")
        return None, timings
    except Exception as e:
        timings["total"] = time.time() - start
        timings["error"] = str(e)
        LOGGER.error(f"Request failed: {e}")
        return None, timings


def run_live_viewer(
    app_name: str,
    crop_json: dict,
    endpoint: str,
    interval: float = 1.0,
):
    """Run the live classification viewer."""

    # Find the target window
    LOGGER.info(f"Searching for window matching '{app_name}'...")
    window_id = find_window_by_app(app_name)

    if window_id is None:
        LOGGER.error(f"Could not find window matching '{app_name}'")
        LOGGER.info("Available windows:")
        for w in list_windows():
            print(f"  - {w['owner']}: {w['name']} ({w['width']}x{w['height']})")
        return

    LOGGER.info(f"Capturing window ID {window_id}")
    LOGGER.info(f"Sending to {endpoint}")
    LOGGER.info("Press 'q' to quit, 'r' to refresh window search")

    # Create display window
    cv2.namedWindow("SAM3 Live Classification", cv2.WINDOW_NORMAL)

    last_capture_time = 0
    last_annotated = None
    frame_count = 0
    total_latency = 0

    while True:
        current_time = time.time()

        # Capture and send at specified interval
        if current_time - last_capture_time >= interval:
            last_capture_time = current_time

            # Capture window
            frame = capture_window(window_id)

            if frame is None:
                LOGGER.warning("Failed to capture window, searching again...")
                window_id = find_window_by_app(app_name)
                if window_id is None:
                    LOGGER.error("Window lost, waiting...")
                    time.sleep(1)
                    continue
                continue

            # Send to server
            annotated, timings = send_to_server(frame, crop_json, endpoint)

            if annotated is not None:
                last_annotated = annotated
                frame_count += 1
                latency = timings.get("total", 0)
                total_latency += latency
                avg_latency = total_latency / frame_count

                # Add timing overlay
                overlay_text = f"Total: {latency:.2f}s | Net: {timings.get('network', 0):.2f}s | {timings.get('size_kb', 0):.0f}KB"
                cv2.putText(
                    last_annotated,
                    overlay_text,
                    (10, last_annotated.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    2,
                )

                LOGGER.info(f"Frame {frame_count}: total={latency:.2f}s net={timings.get('network', 0):.2f}s upload={timings.get('size_kb', 0):.0f}KB")
            else:
                # Show original frame with error overlay
                last_annotated = frame.copy()
                error_msg = timings.get("error", "unknown error")
                cv2.putText(
                    last_annotated,
                    f"Server error: {error_msg}",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 255),
                    2,
                )

        # Display latest frame
        if last_annotated is not None:
            cv2.imshow("SAM3 Live Classification", last_annotated)

        # Handle keyboard input
        key = cv2.waitKey(50) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            LOGGER.info("Refreshing window search...")
            window_id = find_window_by_app(app_name)
            if window_id:
                LOGGER.info(f"Found window ID {window_id}")
            else:
                LOGGER.warning("Window not found")

    cv2.destroyAllWindows()
    LOGGER.info(f"Processed {frame_count} frames, avg latency: {total_latency/max(1,frame_count):.2f}s")


def main():
    parser = argparse.ArgumentParser(description="Live SAM3 Classification Viewer")
    parser.add_argument(
        "--app", "-a",
        help="Application name to capture (partial match, e.g., 'Swann')",
    )
    parser.add_argument(
        "--crop-json", "-c",
        help="Path to crop/annotations JSON file",
    )
    parser.add_argument(
        "--endpoint", "-e",
        default=DEFAULT_ENDPOINT,
        help=f"SAM3 server endpoint (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--interval", "-i",
        type=float,
        default=5.0,
        help="Capture interval in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--list-windows", "-l",
        action="store_true",
        help="List available windows and exit",
    )

    args = parser.parse_args()

    # List windows mode
    if args.list_windows:
        print("Available windows:")
        for w in list_windows():
            print(f"  [{w['id']}] {w['owner']}: {w['name']} ({w['width']}x{w['height']})")
        return

    # Validate required args for live mode
    if not args.app or not args.crop_json:
        parser.error("--app and --crop-json are required (unless using --list-windows)")

    # Load crop JSON
    with open(args.crop_json) as f:
        crop_json = json.load(f)

    LOGGER.info(f"Loaded {len(crop_json.get('tables', []))} tables from {args.crop_json}")

    # Run viewer
    run_live_viewer(
        app_name=args.app,
        crop_json=crop_json,
        endpoint=args.endpoint,
        interval=args.interval,
    )


if __name__ == "__main__":
    main()
