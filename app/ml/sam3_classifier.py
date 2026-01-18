"""
SAM3-based Table State Classifier.

Classifies table states using SAM3 segmentation:
- Occupied: Person detected with mask area > 25% of crop
- Dirty: No person (or small area), but plate(s) detected
- Clean: No person, no plates
"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple, Union

import numpy as np
import torch
from PIL import Image

LOGGER = logging.getLogger("restaurant-ml")

# Detection thresholds
PERSON_THRESHOLD = 0.5
PLATE_THRESHOLD = 0.4

# Area threshold for occupied classification (person mask > 15% of crop)
PERSON_AREA_THRESHOLD = 0.15


class SAM3Classifier:
    """
    Table state classifier using SAM3 segmentation.

    Classification logic:
    1. Detect "person" - if total mask area > 25% of frame -> occupied (stop)
    2. Detect "plate" - if any detected -> dirty
    3. Otherwise -> clean

    Args:
        device: 'cuda', 'mps', 'cpu', or None (auto-detect)
        person_area_threshold: Minimum person mask area ratio to classify as occupied
    """

    def __init__(
        self,
        device: str = None,
        person_area_threshold: float = PERSON_AREA_THRESHOLD,
    ):
        # Auto-detect device
        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        self.device = device
        self.person_area_threshold = person_area_threshold

        # Lazy load model
        self._model = None
        self._processor = None

        # Labels for compatibility with existing interface
        self.id2label = {0: "clean", 1: "dirty", 2: "occupied"}
        self.label2id = {v: k for k, v in self.id2label.items()}

        LOGGER.info("SAM3Classifier initialized (device: %s, person_area_threshold: %.0f%%)",
                    device, person_area_threshold * 100)

    def _load_model(self) -> None:
        """Lazy load SAM3 model."""
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
        LOGGER.info("SAM3 model loaded on %s", self.device)

    @torch.no_grad()
    def _detect_objects(
        self,
        image: Image.Image,
        prompt: str,
        threshold: float = 0.5,
    ) -> Tuple[List[Dict], List[np.ndarray]]:
        """
        Run SAM3 detection for a specific prompt.

        Args:
            image: PIL Image
            prompt: Text prompt (e.g., "person", "plate")
            threshold: Detection confidence threshold

        Returns:
            Tuple of (detections, mask_arrays)
        """
        self._load_model()

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
        scores = results.get("scores", [])

        detections = []
        mask_arrays = []

        if masks is not None and len(masks) > 0:
            for i, mask in enumerate(masks):
                score = scores[i].item() if torch.is_tensor(scores[i]) else scores[i]

                # Convert mask to numpy
                if torch.is_tensor(mask):
                    mask_np = mask.cpu().numpy()
                else:
                    mask_np = mask

                mask_area = int(mask_np.sum())

                detections.append({
                    "score": round(score, 4),
                    "mask_area": mask_area,
                })
                mask_arrays.append(mask_np)

        return detections, mask_arrays

    @torch.no_grad()
    def predict(self, image: Union[str, Image.Image]) -> Dict[str, object]:
        """
        Predict table state from image using SAM3.

        Classification logic:
        1. Detect "person" - if total mask area > 25% of frame -> occupied (stop)
        2. Detect "plate" - if any detected -> dirty
        3. Otherwise -> clean

        Args:
            image: File path or PIL Image

        Returns:
            Dict with 'label', 'confidence', and 'probabilities'
        """
        if isinstance(image, str):
            image = Image.open(image)

        if image.mode != "RGB":
            image = image.convert("RGB")

        # Calculate total pixels for area ratio
        img_width, img_height = image.size
        total_pixels = img_width * img_height

        # Step 1: Check for person - STOP if found
        person_detections, person_masks = self._detect_objects(
            image, "person", PERSON_THRESHOLD
        )

        # Calculate total person mask area
        total_person_area = sum(d["mask_area"] for d in person_detections)
        person_area_ratio = total_person_area / total_pixels if total_pixels > 0 else 0.0

        if person_detections and person_area_ratio >= self.person_area_threshold:
            # Person detected with sufficient area -> occupied, STOP HERE
            confidence = min(0.99, 0.5 + person_area_ratio)
            return {
                "label": "occupied",
                "confidence": round(confidence, 4),
                "probabilities": {
                    "clean": round(0.05, 4),
                    "dirty": round(0.1, 4),
                    "occupied": round(confidence, 4),
                },
                "details": {
                    "person_detections": len(person_detections),
                    "person_area_ratio": round(person_area_ratio, 4),
                    "person_scores": [d["score"] for d in person_detections],
                },
            }

        # Step 2: Check for plates (only if no person)
        plate_detections, plate_masks = self._detect_objects(
            image, "plate", PLATE_THRESHOLD
        )

        if plate_detections:
            # Plates detected -> dirty
            confidence = min(0.95, 0.5 + 0.1 * len(plate_detections))
            return {
                "label": "dirty",
                "confidence": round(confidence, 4),
                "probabilities": {
                    "clean": round(0.1, 4),
                    "dirty": round(confidence, 4),
                    "occupied": round(0.05, 4),
                },
                "details": {
                    "plate_detections": len(plate_detections),
                    "plate_scores": [d["score"] for d in plate_detections],
                },
            }

        # Step 3: Nothing significant detected -> clean
        # If we detected a person but area was too small, note it
        if person_detections:
            confidence = 0.7  # Some person detected but small area
            details = {
                "person_detected_but_small": True,
                "person_area_ratio": round(person_area_ratio, 4),
            }
        else:
            confidence = 0.9  # No person, no plates
            details = {}

        return {
            "label": "clean",
            "confidence": round(confidence, 4),
            "probabilities": {
                "clean": round(confidence, 4),
                "dirty": round(0.1, 4),
                "occupied": round(0.05, 4),
            },
            "details": details,
        }
