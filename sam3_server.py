#!/usr/bin/env python3
"""
SAM3 Classification Server for RunPod.

Receives frames, runs SAM3 classification, returns annotated frames.

Usage:
    python sam3_server.py --port 8000

Client sends:
    POST /classify with multipart form: image file + crop_json

Server returns:
    Annotated image (JPEG) with masks and bounding boxes drawn
"""
from __future__ import annotations

import argparse
import io
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import Response
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)

app = FastAPI(title="SAM3 Classification Server")

# Detection thresholds
PERSON_THRESHOLD = 0.5
PLATE_THRESHOLD = 0.4
PERSON_AREA_THRESHOLD = 0.15
PLATE_AREA_THRESHOLD = 0.005

# Visualization colors (BGR)
STATE_COLORS = {
    "clean": (0, 200, 0),
    "occupied": (0, 200, 255),
    "dirty": (0, 0, 200),
    "unknown": (128, 128, 128),
}
PERSON_MASK_COLOR = (255, 100, 100)
PLATE_MASK_COLOR = (100, 100, 255)
FILL_OPACITY = 0.3
MASK_OPACITY = 0.4

# Global detector
detector = None
# State history for temporal smoothing (per table)
state_history: Dict[str, List[str]] = {}
smoothed_states: Dict[str, str] = {}
CONSENSUS_WINDOW = 2


class SAM3Detector:
    def __init__(self, device: str = "cuda"):
        self.device = device
        self._model = None
        self._processor = None

    def load_model(self):
        if self._model is not None:
            return

        from transformers import Sam3Model, Sam3Processor

        LOGGER.info("Loading SAM3 model...")
        self._processor = Sam3Processor.from_pretrained("facebook/sam3")
        self._model = Sam3Model.from_pretrained("facebook/sam3")
        self._model = self._model.to(self.device, dtype=torch.bfloat16)
        self._model.eval()
        LOGGER.info(f"SAM3 loaded on {self.device}")

    @torch.no_grad()
    def detect(self, image: Image.Image, prompt: str, threshold: float) -> List[np.ndarray]:
        self.load_model()

        if image.mode != "RGB":
            image = image.convert("RGB")

        inputs = self._processor(images=image, text=prompt, return_tensors="pt").to(self.device)
        outputs = self._model(**inputs)

        results = self._processor.post_process_instance_segmentation(
            outputs, threshold=threshold, mask_threshold=0.5,
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


def create_bbox_mask(bbox: Dict, height: int, width: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    if "corners" in bbox:
        pts = np.array(bbox["corners"], dtype=np.int32)
        cv2.fillPoly(mask, [pts], 1)
    elif "center" in bbox and "size" in bbox:
        cx, cy = bbox["center"]
        w, h = bbox["size"]
        x1, y1 = max(0, int(cx - w/2)), max(0, int(cy - h/2))
        x2, y2 = min(width, int(cx + w/2)), min(height, int(cy + h/2))
        mask[y1:y2, x1:x2] = 1
    return mask.astype(bool)


def classify_tables(tables: List[Dict], person_masks: List[np.ndarray],
                    plate_masks: List[np.ndarray], height: int, width: int) -> Dict[str, Dict]:
    results = {}

    combined_person = None
    if person_masks:
        combined_person = np.zeros((height, width), dtype=bool)
        for pm in person_masks:
            combined_person = np.logical_or(combined_person, pm)

    combined_plate = None
    if plate_masks:
        combined_plate = np.zeros((height, width), dtype=bool)
        for pm in plate_masks:
            combined_plate = np.logical_or(combined_plate, pm)

    for table in tables:
        table_num = f"T{table.get('id', '?')}"
        bbox = table.get("rotated_bbox", table.get("bbox"))

        if not bbox:
            results[table_num] = {"state": "unknown", "confidence": 0.0}
            continue

        bbox_mask = create_bbox_mask(bbox, height, width)
        bbox_area = int(bbox_mask.sum())

        if bbox_area == 0:
            results[table_num] = {"state": "unknown", "confidence": 0.0}
            continue

        person_ratio = 0.0
        if combined_person is not None:
            person_intersection = int(np.logical_and(bbox_mask, combined_person).sum())
            person_ratio = person_intersection / bbox_area

        if person_ratio >= PERSON_AREA_THRESHOLD:
            confidence = min(0.99, 0.5 + person_ratio)
            results[table_num] = {"state": "occupied", "confidence": confidence, "person_ratio": person_ratio}
        else:
            plate_ratio = 0.0
            if combined_plate is not None:
                plate_intersection = int(np.logical_and(bbox_mask, combined_plate).sum())
                plate_ratio = plate_intersection / bbox_area

            if plate_ratio >= PLATE_AREA_THRESHOLD:
                confidence = min(0.95, 0.5 + plate_ratio * 2)
                results[table_num] = {"state": "dirty", "confidence": confidence, "plate_ratio": plate_ratio}
            else:
                confidence = 0.9 if person_ratio == 0 else 0.7
                results[table_num] = {"state": "clean", "confidence": confidence}

    return results


def apply_consensus(table_num: str, raw_state: str) -> str:
    global state_history, smoothed_states

    if table_num not in state_history:
        state_history[table_num] = []
        smoothed_states[table_num] = "unknown"

    state_history[table_num].append(raw_state)

    # Keep only recent history
    if len(state_history[table_num]) > 20:
        state_history[table_num] = state_history[table_num][-20:]

    if len(state_history[table_num]) >= CONSENSUS_WINDOW:
        recent = state_history[table_num][-CONSENSUS_WINDOW:]
        if len(set(recent)) == 1:
            smoothed_states[table_num] = recent[0]

    return smoothed_states[table_num]


def draw_annotated_frame(
    frame: np.ndarray,
    tables: List[Dict],
    classifications: Dict[str, Dict],
    person_mask: Optional[np.ndarray],
    plate_mask: Optional[np.ndarray],
) -> np.ndarray:
    height, width = frame.shape[:2]

    # Draw masks first
    overlay = frame.copy()
    if person_mask is not None and person_mask.any():
        overlay[person_mask] = PERSON_MASK_COLOR
    if plate_mask is not None and plate_mask.any():
        overlay[plate_mask] = PLATE_MASK_COLOR
    frame = cv2.addWeighted(overlay, MASK_OPACITY, frame, 1 - MASK_OPACITY, 0)

    # Draw bounding boxes
    for table in tables:
        table_num = f"T{table.get('id', '?')}"
        bbox = table.get("rotated_bbox", table.get("bbox"))
        if not bbox:
            continue

        classification = classifications.get(table_num, {})
        raw_state = classification.get("state", "unknown")
        confidence = classification.get("confidence", 0.0)

        # Use raw state directly (no temporal smoothing)
        color = STATE_COLORS.get(raw_state, STATE_COLORS["unknown"])

        # Get corners
        if "corners" in bbox:
            corners = bbox["corners"]
        else:
            cx, cy = bbox["center"]
            w, h = bbox["size"]
            corners = [[cx-w/2, cy-h/2], [cx+w/2, cy-h/2], [cx+w/2, cy+h/2], [cx-w/2, cy+h/2]]

        pts = np.array(corners, dtype=np.int32)

        # Semi-transparent fill
        overlay = frame.copy()
        cv2.fillPoly(overlay, [pts], color)
        frame = cv2.addWeighted(overlay, FILL_OPACITY, frame, 1 - FILL_OPACITY, 0)

        # Border
        cv2.polylines(frame, [pts], True, color, 2)

        # Label
        label = f"{table_num}: {raw_state} ({confidence:.0%})"

        min_x = int(min(c[0] for c in corners))
        min_y = int(min(c[1] for c in corners))

        font = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th), _ = cv2.getTextSize(label, font, 0.6, 2)
        lx, ly = max(0, min_x), max(th + 4, min_y - 4)
        cv2.rectangle(frame, (lx, ly - th - 4), (lx + tw + 4, ly + 4), color, -1)
        cv2.putText(frame, label, (lx + 2, ly), font, 0.6, (255, 255, 255), 2)

    # Legend
    cv2.putText(frame, "Blue=Person", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, PERSON_MASK_COLOR, 1)
    cv2.putText(frame, "Red=Plate", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, PLATE_MASK_COLOR, 1)

    return frame


@app.on_event("startup")
def startup():
    global detector
    LOGGER.info("Initializing SAM3 detector...")
    detector = SAM3Detector(device="cuda" if torch.cuda.is_available() else "cpu")
    detector.load_model()

    # Warmup
    LOGGER.info("Warming up...")
    dummy = Image.new("RGB", (640, 480))
    detector.detect(dummy, "person", 0.5)
    LOGGER.info("Server ready!")


@app.get("/health")
def health():
    return {"status": "ok", "gpu": torch.cuda.is_available(), "device": detector.device if detector else None}


@app.post("/classify")
async def classify(
    image: UploadFile = File(...),
    crop_json: str = Form(...),
):
    """
    Classify tables in an image and return annotated image.

    Args:
        image: Image file (JPEG/PNG)
        crop_json: JSON string with table bounding boxes

    Returns:
        Annotated JPEG image
    """
    # Parse crop_json
    try:
        crop_data = json.loads(crop_json)
        if "crop_json" in crop_data:
            crop_data = crop_data["crop_json"]
        tables = crop_data.get("tables", [])
    except json.JSONDecodeError as e:
        return Response(content=f"Invalid crop_json: {e}", status_code=400)

    # Load image
    image_bytes = await image.read()
    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    width, height = pil_image.size

    # Run detection
    LOGGER.info(f"Processing frame {width}x{height} with {len(tables)} tables...")
    person_masks = detector.detect(pil_image, "person", PERSON_THRESHOLD)
    plate_masks = detector.detect(pil_image, "plate", PLATE_THRESHOLD)
    LOGGER.info(f"  Found {len(person_masks)} person(s), {len(plate_masks)} plate(s)")

    # Combine masks
    combined_person = None
    if person_masks:
        combined_person = np.zeros((height, width), dtype=bool)
        for pm in person_masks:
            combined_person = np.logical_or(combined_person, pm)

    combined_plate = None
    if plate_masks:
        combined_plate = np.zeros((height, width), dtype=bool)
        for pm in plate_masks:
            combined_plate = np.logical_or(combined_plate, pm)

    # Classify tables
    classifications = classify_tables(tables, person_masks, plate_masks, height, width)

    # Draw annotations
    frame = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    annotated = draw_annotated_frame(frame, tables, classifications, combined_person, combined_plate)

    # Encode as JPEG
    _, jpeg_bytes = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])

    return Response(content=jpeg_bytes.tobytes(), media_type="image/jpeg")


@app.post("/classify_json")
async def classify_json(
    image: UploadFile = File(...),
    crop_json: str = Form(...),
):
    """Return JSON classification results instead of annotated image."""
    try:
        crop_data = json.loads(crop_json)
        if "crop_json" in crop_data:
            crop_data = crop_data["crop_json"]
        tables = crop_data.get("tables", [])
    except json.JSONDecodeError as e:
        return {"error": f"Invalid crop_json: {e}"}

    image_bytes = await image.read()
    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    width, height = pil_image.size

    person_masks = detector.detect(pil_image, "person", PERSON_THRESHOLD)
    plate_masks = detector.detect(pil_image, "plate", PLATE_THRESHOLD)

    classifications = classify_tables(tables, person_masks, plate_masks, height, width)

    # Apply smoothing and build response
    results = {}
    for table_num, cls in classifications.items():
        raw_state = cls["state"]
        smoothed = apply_consensus(table_num, raw_state)
        results[table_num] = {
            "raw_state": raw_state,
            "smoothed_state": smoothed,
            "confidence": cls.get("confidence", 0.0),
        }

    return {
        "person_count": len(person_masks),
        "plate_count": len(plate_masks),
        "tables": results,
    }


@app.post("/reset")
def reset_state():
    """Reset temporal smoothing state."""
    global state_history, smoothed_states
    state_history = {}
    smoothed_states = {}
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
