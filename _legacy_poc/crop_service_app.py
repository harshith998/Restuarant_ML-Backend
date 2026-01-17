from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from crop_service import CropService

app = FastAPI(title="Restaurant Crop Service")
service = CropService.from_env()


class CameraRegisterPayload(BaseModel):
    camera_id: str = Field(..., min_length=1)
    video_source: str = Field(..., min_length=1)
    crop_json: Optional[Dict[str, Any]] = None


class CropJsonPayload(BaseModel):
    crop_json: Dict[str, Any]


@app.on_event("startup")
async def startup() -> None:
    await service.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await service.stop()


@app.get("/healthz")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/cameras")
def list_cameras() -> Dict[str, Any]:
    cameras = [
        {
            "camera_id": cam.camera_id,
            "video_source": cam.video_source,
            "last_capture_ts": cam.last_capture_ts,
            "last_frame_index": cam.last_frame_index,
            "has_crop_json": cam.crop_json is not None,
        }
        for cam in service.list_cameras()
    ]
    return {"cameras": cameras}


@app.post("/cameras/register")
def register_camera(payload: CameraRegisterPayload) -> Dict[str, str]:
    service.register_camera(
        camera_id=payload.camera_id,
        video_source=payload.video_source,
        crop_json=payload.crop_json,
    )
    return {"status": "registered"}


@app.post("/cameras/{camera_id}/crop-json")
def update_crop_json(camera_id: str, payload: CropJsonPayload) -> Dict[str, str]:
    try:
        service.update_crop_json(camera_id=camera_id, crop_json=payload.crop_json)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "updated"}


@app.post("/cameras/{camera_id}/refresh")
def refresh_crop_json(camera_id: str) -> Dict[str, str]:
    try:
        service.refresh_crop_json(camera_id=camera_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "refresh_requested"}
