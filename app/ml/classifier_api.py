"""
FastAPI endpoints for ML table state classification.

Provides /predict endpoint for classifying table images.
Optionally updates table state in Postgres when table_id is provided.
"""
from __future__ import annotations

import io
import logging
import os
from typing import Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.inference import TableClassifier
from app.database import get_session
from app.services.table_state import update_table_state

LOGGER = logging.getLogger("restaurant-ml")

router = APIRouter(prefix="/ml", tags=["ml"])


class ModelManager:
    """Manages ML model lifecycle."""

    def __init__(self) -> None:
        self.classifier: Optional[TableClassifier] = None

    def load(self, weights_path: str = None, device: str = None) -> None:
        """Load the classifier model."""
        if weights_path is None:
            weights_path = os.getenv("WEIGHTS_PATH", "weights/dinov3_classifier.pt")
        if device is None:
            device = os.getenv("MODEL_DEVICE")

        LOGGER.info("Loading classifier from %s", weights_path)
        self.classifier = TableClassifier(weights_path, device=device)

    def predict(self, image: Image.Image) -> Dict[str, object]:
        """Run prediction on an image."""
        if self.classifier is None:
            raise RuntimeError("Model not loaded.")
        return self.classifier.predict(image)

    @property
    def is_loaded(self) -> bool:
        return self.classifier is not None


# Global model manager instance
model_manager = ModelManager()


@router.get("/healthz")
def ml_health() -> Dict[str, str]:
    """ML service health check."""
    return {
        "status": "ok",
        "model_loaded": model_manager.is_loaded,
    }


@router.post("/predict")
async def predict(
    file: UploadFile = File(...),
    table_id: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, object]:
    """
    Classify table state from uploaded image.

    Args:
        file: Image file to classify
        table_id: Optional UUID of the table. If provided, updates the table
                  state in Postgres and creates a TableStateLog entry.

    Returns:
        label: Predicted state (clean, occupied, dirty)
        confidence: Prediction confidence
        probabilities: All class probabilities
        table_updated: Whether the table state was updated in DB (if table_id provided)
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Only image uploads are supported.")

    payload = await file.read()
    try:
        image = Image.open(io.BytesIO(payload)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to read image file.")

    try:
        result = model_manager.predict(image)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    # If table_id provided, update the table state in Postgres
    if table_id:
        try:
            table_uuid = UUID(table_id)
            await update_table_state(
                session=session,
                table_id=table_uuid,
                new_state=result["label"],
                confidence=result["confidence"],
                source="ml",
            )
            await session.commit()
            result["table_updated"] = True
            result["table_id"] = table_id
            LOGGER.info(
                "Updated table %s state to %s (confidence: %.2f)",
                table_id, result["label"], result["confidence"]
            )
        except ValueError as exc:
            # Table not found - still return prediction but note the error
            result["table_updated"] = False
            result["table_update_error"] = str(exc)
            LOGGER.warning("Could not update table state: %s", exc)
        except Exception as exc:
            # Other DB errors - still return prediction
            result["table_updated"] = False
            result["table_update_error"] = f"Database error: {str(exc)}"
            LOGGER.error("Database error updating table state: %s", exc)

    return result


def init_model(weights_path: str = None, device: str = None) -> None:
    """Initialize the ML model (call during app startup)."""
    model_manager.load(weights_path, device)
    LOGGER.info("ML model loaded and ready.")
