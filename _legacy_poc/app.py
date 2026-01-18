import io
import logging
import os
from typing import Dict, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image

from inference import TableClassifier

LOGGER = logging.getLogger("restaurant-ml")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


class ModelManager:
    def __init__(self) -> None:
        self.classifier: Optional[TableClassifier] = None

    def load(self) -> None:
        weights_path = os.getenv("WEIGHTS_PATH", "/app/weights/dinov3_classifier.pt")
        device = os.getenv("MODEL_DEVICE")
        LOGGER.info("Loading classifier from %s", weights_path)
        self.classifier = TableClassifier(weights_path, device=device)

    def predict(self, image: Image.Image) -> Dict[str, object]:
        if self.classifier is None:
            raise RuntimeError("Model not loaded.")
        return self.classifier.predict(image)


app = FastAPI(title="Restaurant ML - Table State Classifier")
model_manager = ModelManager()


@app.on_event("startup")
def startup() -> None:
    model_manager.load()
    LOGGER.info("Model loaded and ready.")


@app.get("/healthz")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/predict")
async def predict(file: UploadFile = File(...)) -> Dict[str, object]:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Only image uploads are supported.")

    payload = await file.read()
    try:
        image = Image.open(io.BytesIO(payload)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to read image file.")

    try:
        return model_manager.predict(image)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
