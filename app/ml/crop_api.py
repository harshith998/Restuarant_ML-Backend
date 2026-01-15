"""
FastAPI endpoints for crop service management.

Provides camera registration and crop JSON management endpoints.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.ml.crop_service import CropService

router = APIRouter(prefix="/crops", tags=["crops"])

# Global service instance (initialized during app startup)
_service: Optional[CropService] = None


class CameraRegisterPayload(BaseModel):
    """Payload for registering a camera."""
    camera_id: str = Field(..., min_length=1)
    video_source: str = Field(..., min_length=1)
    crop_json: Optional[Dict[str, Any]] = None


class CropJsonPayload(BaseModel):
    """Payload for updating crop JSON."""
    crop_json: Dict[str, Any]


def get_service() -> CropService:
    """Get the crop service instance."""
    if _service is None:
        raise RuntimeError("Crop service not initialized")
    return _service


def init_service(service: CropService = None) -> CropService:
    """Initialize the crop service (call during app startup)."""
    global _service
    if service is None:
        service = CropService.from_env()
    _service = service
    return _service


@router.get("/healthz")
async def crop_health() -> Dict[str, str]:
    """Crop service health check."""
    return {"status": "ok"}


@router.get("/cameras")
async def list_cameras() -> Dict[str, Any]:
    """List all registered cameras."""
    service = get_service()
    cameras = [
        {
            "camera_id": cam.camera_id,
            "video_source": cam.video_source,
            "last_capture_ts": cam.last_capture_ts,
            "last_frame_index": cam.last_frame_index,
            "has_crop_json": cam.crop_json is not None,
        }
        for cam in await service.list_cameras()
    ]
    return {"cameras": cameras}


@router.post("/cameras/register")
async def register_camera(payload: CameraRegisterPayload) -> Dict[str, str]:
    """Register a new camera."""
    service = get_service()
    await service.register_camera(
        camera_id=payload.camera_id,
        video_source=payload.video_source,
        crop_json=payload.crop_json,
    )
    return {"status": "registered"}


@router.post("/cameras/{camera_id}/crop-json")
async def update_crop_json(camera_id: str, payload: CropJsonPayload) -> Dict[str, str]:
    """Update crop JSON for a camera."""
    service = get_service()
    try:
        await service.update_crop_json(camera_id=camera_id, crop_json=payload.crop_json)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "updated"}


@router.post("/cameras/{camera_id}/refresh")
async def refresh_crop_json(camera_id: str) -> Dict[str, str]:
    """Request crop JSON refresh for a camera."""
    service = get_service()
    try:
        await service.refresh_crop_json(camera_id=camera_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "refresh_requested"}
