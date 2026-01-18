#!/usr/bin/env python3
"""
Test script for video upload pipeline.

Usage:
    python scripts/test_video_pipeline.py /path/to/video_folder

The folder should contain:
    - *.mp4 video file
    - frame_000000/annotations.json with table crops
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"
TIMEOUT = 60.0


def find_video_file(folder: Path) -> Path | None:
    """Find the MP4 file in the folder."""
    for ext in [".mp4", ".mov", ".avi", ".mkv", ".webm"]:
        files = list(folder.glob(f"*{ext}"))
        if files:
            return files[0]
    return None


def find_annotations(folder: Path) -> Path | None:
    """Find the annotations.json file."""
    # Try frame_000000/annotations.json first
    ann_path = folder / "frame_000000" / "annotations.json"
    if ann_path.exists():
        return ann_path

    # Try direct annotations.json
    ann_path = folder / "annotations.json"
    if ann_path.exists():
        return ann_path

    return None


def check_server() -> bool:
    """Check if server is running."""
    try:
        resp = httpx.get(f"{BASE_URL}/healthz", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False


def upload_video(video_path: Path, fps: float = 1.0) -> dict:
    """Upload video and return job info."""
    print(f"\n[1/5] Uploading video: {video_path.name}")
    print(f"      Size: {video_path.stat().st_size / 1024 / 1024:.1f} MB")

    with open(video_path, "rb") as f:
        files = {"file": (video_path.name, f, "video/mp4")}
        data = {"fps": str(fps)}

        resp = httpx.post(
            f"{BASE_URL}/api/v1/videos/upload",
            files=files,
            data=data,
            timeout=TIMEOUT,
        )

    if resp.status_code != 201:
        print(f"      ERROR: {resp.status_code} - {resp.text}")
        return None

    result = resp.json()
    print(f"      Job ID: {result['job_id']}")
    print(f"      Status: {result['status']}")
    return result


def wait_for_completion(job_id: str, max_wait: int = 300) -> dict:
    """Poll job status until completed."""
    print(f"\n[2/5] Waiting for frame extraction...")

    start = time.time()
    last_progress = -1

    while time.time() - start < max_wait:
        resp = httpx.get(f"{BASE_URL}/api/v1/videos/{job_id}", timeout=10.0)
        if resp.status_code != 200:
            print(f"      ERROR: {resp.status_code} - {resp.text}")
            return None

        job = resp.json()
        status = job["status"]
        progress = job.get("progress_percent", 0)
        frames = job.get("frames_extracted", 0)

        if progress != last_progress:
            print(f"      Status: {status} | Progress: {progress}% | Frames: {frames}")
            last_progress = progress

        if status == "completed":
            print(f"      Completed in {time.time() - start:.1f}s")
            print(f"      Duration: {job.get('duration_seconds', 0):.1f}s")
            print(f"      Resolution: {job.get('width')}x{job.get('height')}")
            print(f"      FPS: {job.get('fps')}")
            return job

        if status == "failed":
            print(f"      FAILED: {job.get('error_message')}")
            return None

        time.sleep(1)

    print(f"      TIMEOUT after {max_wait}s")
    return None


def list_frames(job_id: str) -> dict:
    """List extracted frames."""
    print(f"\n[3/5] Listing extracted frames...")

    resp = httpx.get(f"{BASE_URL}/api/v1/videos/{job_id}/frames", timeout=10.0)
    if resp.status_code != 200:
        print(f"      ERROR: {resp.status_code} - {resp.text}")
        return None

    result = resp.json()
    total = result["total_frames"]
    print(f"      Total frames: {total}")

    if total > 0:
        first_frame = result["frames"][0]
        print(f"      First frame URL: {first_frame['url']}")

    return result


def run_classification(job_id: str, annotations_path: Path, update_db: bool = False) -> dict:
    """Run classification with crop JSON."""
    print(f"\n[4/5] Running classification...")
    print(f"      Annotations: {annotations_path}")

    # Load annotations
    with open(annotations_path) as f:
        annotations = json.load(f)

    tables = annotations.get("tables", [])
    print(f"      Tables found: {len(tables)}")

    # Build crop_json in expected format
    crop_json = {"tables": []}
    for table in tables:
        crop_json["tables"].append({
            "table_id": None,  # No DB table linked
            "table_number": f"T{table['id']}",
            "rotated_bbox": table["rotated_bbox"],
        })

    # Call process endpoint
    payload = {
        "crop_json": crop_json,
        "update_db": update_db,
        "process_every_n": 1,
    }

    try:
        resp = httpx.post(
            f"{BASE_URL}/api/v1/videos/{job_id}/process",
            json=payload,
            timeout=TIMEOUT,
        )
    except Exception as e:
        print(f"      ERROR: {e}")
        return None

    if resp.status_code == 202:
        result = resp.json()
        print(f"      Process started!")
        print(f"      Frames to process: {result.get('frames_to_process')}")
        print(f"      Tables: {result.get('tables_count')}")
        return result
    else:
        print(f"      ERROR: {resp.status_code} - {resp.text}")
        return None


def get_results(job_id: str) -> dict:
    """Get classification results."""
    print(f"\n[5/5] Getting results...")

    # Wait a bit for background processing
    print("      Waiting for classification to complete...")
    time.sleep(3)

    resp = httpx.get(
        f"{BASE_URL}/api/v1/videos/{job_id}/results",
        params={"include_per_frame": "false"},
        timeout=30.0,
    )

    if resp.status_code != 200:
        print(f"      ERROR: {resp.status_code} - {resp.text}")
        return None

    result = resp.json()
    frames_processed = result.get("frames_processed", 0)
    tables_updated = result.get("tables_updated", 0)
    summary = result.get("summary", {})

    print(f"      Frames processed: {frames_processed}")
    print(f"      Tables updated: {tables_updated}")

    if summary:
        print(f"\n      Table States:")
        for table_num, data in summary.items():
            state = data.get("final_state", "unknown")
            changes = len(data.get("state_changes", []))
            print(f"        {table_num}: {state} ({changes} state changes)")

    return result


def main():
    parser = argparse.ArgumentParser(description="Test video pipeline")
    parser.add_argument("folder", type=Path, help="Folder containing video and annotations")
    parser.add_argument("--fps", type=float, default=1.0, help="Frame extraction rate")
    parser.add_argument("--update-db", action="store_true", help="Update table states in DB")
    args = parser.parse_args()

    folder = args.folder
    if not folder.exists():
        print(f"ERROR: Folder not found: {folder}")
        sys.exit(1)

    # Find files
    video_path = find_video_file(folder)
    if not video_path:
        print(f"ERROR: No video file found in {folder}")
        sys.exit(1)

    annotations_path = find_annotations(folder)
    if not annotations_path:
        print(f"ERROR: No annotations.json found in {folder}")
        sys.exit(1)

    print("=" * 60)
    print("VIDEO PIPELINE TEST")
    print("=" * 60)
    print(f"Folder: {folder}")
    print(f"Video: {video_path.name}")
    print(f"Annotations: {annotations_path}")
    print(f"FPS: {args.fps}")

    # Check server
    print("\n[0/5] Checking server...")
    if not check_server():
        print("      ERROR: Server not running at", BASE_URL)
        print("      Start with: ML_ENABLED=true uvicorn app.main:app --port 8000")
        sys.exit(1)
    print("      Server OK")

    # Step 1: Upload
    upload_result = upload_video(video_path, args.fps)
    if not upload_result:
        sys.exit(1)

    job_id = upload_result["job_id"]

    # Step 2: Wait for extraction
    job_result = wait_for_completion(job_id)
    if not job_result:
        sys.exit(1)

    # Step 3: List frames
    frames_result = list_frames(job_id)
    if not frames_result:
        sys.exit(1)

    # Step 4: Run classification
    process_result = run_classification(job_id, annotations_path, args.update_db)
    if not process_result:
        print("\n      Classification failed (ML model may not be loaded)")
        print("      Steps 1-3 completed successfully!")
        print(f"\n      Job ID: {job_id}")
        print(f"      To retry classification once ML is ready:")
        print(f"      curl -X POST {BASE_URL}/api/v1/videos/{job_id}/process ...")
        sys.exit(0)

    # Step 5: Get results
    results = get_results(job_id)

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print(f"Job ID: {job_id}")
    print(f"Frames extracted: {job_result.get('frames_extracted', 0)}")
    if results:
        print(f"Frames classified: {results.get('frames_processed', 0)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
