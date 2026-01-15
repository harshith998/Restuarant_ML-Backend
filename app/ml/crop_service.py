"""
Crop Service for camera management and classifier dispatch.

Manages camera registrations, crop JSON updates, and periodic dispatch
of table crops to the classifier service.

Features:
- Frame capture from HTTP URLs or local files
- Axis-aligned crop extraction from rotated bounding boxes
- Retry with exponential backoff for classifier dispatch
- In-flight limiting per camera
"""
from __future__ import annotations

import asyncio
import io
import logging
import mimetypes
import os
import shlex
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import request

from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session_context
from app.models.crop import CameraCropState, CameraSource, CropDispatchLog
LOGGER = logging.getLogger("crop-service")


@dataclass
class CropServiceConfig:
    """Configuration for the crop service."""

    classifier_endpoint: str
    classifier_timeout_seconds: int
    capture_interval_seconds: int
    crops_base_dir: Path
    video_source_timeout_seconds: int
    max_in_flight_per_camera: int
    dispatch_max_attempts: int
    dispatch_backoff_seconds: float
    refresh_command: str
    refresh_timeout_seconds: int


@dataclass
class CameraConfig:
    """Configuration for a registered camera."""

    camera_id: str
    video_source: str
    crop_json: Optional[Dict[str, Any]] = None
    last_capture_ts: float = 0.0
    last_frame_index: Optional[int] = None
    last_dispatched_frame_index: Dict[str, int] = field(default_factory=dict)

class CameraRegistry:
    """Registry of cameras and their configurations."""

    @staticmethod
    def _to_camera_config(source: CameraSource, state: Optional[CameraCropState]) -> CameraConfig:
        last_capture_ts = 0.0
        if state and state.last_capture_ts:
            last_capture_ts = state.last_capture_ts.timestamp()

        return CameraConfig(
            camera_id=source.camera_id,
            video_source=source.video_source,
            crop_json=state.crop_json if state else None,
            last_capture_ts=last_capture_ts,
            last_frame_index=state.last_frame_index if state else None,
            last_dispatched_frame_index=state.last_dispatched_frame_index if state else {},
        )

    async def list_all(self, session: AsyncSession) -> List[CameraConfig]:
        stmt = select(CameraSource, CameraCropState).outerjoin(
            CameraCropState, CameraCropState.camera_id == CameraSource.camera_id
        )
        result = await session.execute(stmt)
        cameras = []
        for source, state in result.all():
            cameras.append(self._to_camera_config(source, state))
        return cameras

    async def get(self, session: AsyncSession, camera_id: str) -> CameraConfig:
        stmt = (
            select(CameraSource, CameraCropState)
            .outerjoin(CameraCropState, CameraCropState.camera_id == CameraSource.camera_id)
            .where(CameraSource.camera_id == camera_id)
        )
        result = await session.execute(stmt)
        row = result.first()
        if not row:
            raise KeyError(f"Camera '{camera_id}' not registered.")
        source, state = row
        return self._to_camera_config(source, state)

    async def register(
        self,
        session: AsyncSession,
        camera_id: str,
        video_source: str,
        crop_json: Optional[Dict[str, Any]],
    ) -> CameraConfig:
        source = await session.get(CameraSource, camera_id)
        if source is None:
            source = CameraSource(camera_id=camera_id, video_source=video_source)
            session.add(source)
        else:
            source.video_source = video_source

        state = await session.get(CameraCropState, camera_id)
        if state is None:
            state = CameraCropState(camera_id=camera_id, last_dispatched_frame_index={})
            session.add(state)

        if crop_json is not None:
            state.crop_json = crop_json
            state.last_frame_index = crop_json.get("frame_index")
            state.updated_at = datetime.utcnow()

        await session.flush()
        return self._to_camera_config(source, state)

    async def update_crop_json(
        self, session: AsyncSession, camera_id: str, crop_json: Dict[str, Any]
    ) -> CameraConfig:
        source = await session.get(CameraSource, camera_id)
        if source is None:
            raise KeyError(f"Camera '{camera_id}' not registered.")

        state = await session.get(CameraCropState, camera_id)
        if state is None:
            state = CameraCropState(camera_id=camera_id, last_dispatched_frame_index={})
            session.add(state)

        state.crop_json = crop_json
        state.last_frame_index = crop_json.get("frame_index")
        state.updated_at = datetime.utcnow()
        await session.flush()
        return self._to_camera_config(source, state)

    async def update_capture_state(
        self,
        session: AsyncSession,
        camera_id: str,
        last_capture_ts: datetime,
        last_frame_index: Optional[int],
        last_dispatched_frame_index: Dict[str, int],
        crop_json: Optional[Dict[str, Any]] = None,
    ) -> None:
        source = await session.get(CameraSource, camera_id)
        if source is None:
            raise KeyError(f"Camera '{camera_id}' not registered.")

        state = await session.get(CameraCropState, camera_id)
        if state is None:
            state = CameraCropState(camera_id=camera_id, last_dispatched_frame_index={})
            session.add(state)

        state.last_capture_ts = last_capture_ts
        state.last_frame_index = last_frame_index
        state.last_dispatched_frame_index = last_dispatched_frame_index or {}
        if crop_json is not None:
            state.crop_json = crop_json
        state.updated_at = datetime.utcnow()
        await session.flush()

    async def log_dispatches(
        self,
        session: AsyncSession,
        camera_id: str,
        dispatch_records: List[Dict[str, Any]],
    ) -> None:
        if not dispatch_records:
            return
        logs = [
            CropDispatchLog(
                camera_id=camera_id,
                table_id=record["table_id"],
                frame_index=record["frame_index"],
                dispatched_at=record["dispatched_at"],
                status=record["status"],
            )
            for record in dispatch_records
        ]
        session.add_all(logs)
        await session.flush()


class ClassifierClient:
    """HTTP client for dispatching crops to classifier."""

    def __init__(self, endpoint: str, timeout_seconds: int = 10) -> None:
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds

    def send_crop(
        self,
        crop_path: Path,
        camera_id: str,
        table_id: int,
        frame_index: Optional[int],
        video_name: Optional[str],
    ) -> bool:
        if not self._endpoint:
            LOGGER.info("Classifier endpoint not configured; skipping dispatch.")
            return False

        if not crop_path.exists():
            LOGGER.warning("Crop file missing: %s", crop_path)
            return False

        content_type = mimetypes.guess_type(crop_path.name)[0] or "application/octet-stream"
        with crop_path.open("rb") as handle:
            file_bytes = handle.read()

        fields = {
            "camera_id": camera_id,
            "table_id": table_id,
            "frame_index": frame_index if frame_index is not None else "",
            "video_name": video_name or "",
        }
        body, boundary = _encode_multipart(
            fields, ("file", crop_path.name, content_type, file_bytes)
        )
        req = request.Request(self._endpoint, data=body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        req.add_header("Content-Length", str(len(body)))

        try:
            with request.urlopen(req, timeout=self._timeout_seconds) as resp:
                status = resp.status
        except Exception as exc:
            LOGGER.warning("Classifier dispatch failed: %s", exc)
            return False

        return 200 <= status < 300

    def send_crop_with_retry(
        self,
        crop_path: Path,
        camera_id: str,
        table_id: int,
        frame_index: Optional[int],
        video_name: Optional[str],
        max_attempts: int,
        backoff_seconds: float,
    ) -> bool:
        """Send crop with exponential backoff retry."""
        for attempt in range(1, max_attempts + 1):
            sent = self.send_crop(
                crop_path=crop_path,
                camera_id=camera_id,
                table_id=table_id,
                frame_index=frame_index,
                video_name=video_name,
            )
            if sent:
                return True
            if attempt < max_attempts:
                sleep_seconds = backoff_seconds * (2 ** (attempt - 1))
                time.sleep(sleep_seconds)
        return False


class FrameCapture:
    """Captures frames from HTTP URLs or local files."""

    def __init__(self, timeout_seconds: int) -> None:
        self._timeout_seconds = timeout_seconds

    def capture(self, video_source: str) -> Image.Image:
        if video_source.startswith(("http://", "https://")):
            with request.urlopen(video_source, timeout=self._timeout_seconds) as resp:
                data = resp.read()
            image = Image.open(io.BytesIO(data))
        else:
            source_path = Path(video_source)
            if not source_path.exists():
                raise FileNotFoundError(f"Video source not found: {video_source}")
            image = Image.open(source_path)

        if image.mode != "RGB":
            image = image.convert("RGB")
        return image


def _encode_multipart(
    fields: Dict[str, Any],
    file_part: tuple,
) -> tuple:
    """Encode multipart form data."""
    boundary = uuid.uuid4().hex
    lines: List[bytes] = []

    for name, value in fields.items():
        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="{name}"'.encode("utf-8"))
        lines.append(b"")
        lines.append(str(value).encode("utf-8"))

    field_name, filename, content_type, data = file_part
    lines.append(f"--{boundary}".encode("utf-8"))
    lines.append(
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'.encode(
            "utf-8"
        )
    )
    lines.append(f"Content-Type: {content_type}".encode("utf-8"))
    lines.append(b"")
    lines.append(data)
    lines.append(f"--{boundary}--".encode("utf-8"))
    lines.append(b"")

    body = b"\r\n".join(lines)
    return body, boundary


def _axis_aligned_bbox(
    rotated_bbox: Dict[str, Any],
    frame_width: int,
    frame_height: int,
) -> Optional[Tuple[int, int, int, int]]:
    """Convert rotated bbox to axis-aligned (left, upper, right, lower)."""
    corners = rotated_bbox.get("corners") or []
    if corners:
        xs = [point[0] for point in corners if len(point) >= 2]
        ys = [point[1] for point in corners if len(point) >= 2]
        if not xs or not ys:
            return None
        left, right = min(xs), max(xs)
        upper, lower = min(ys), max(ys)
    else:
        center = rotated_bbox.get("center")
        size = rotated_bbox.get("size")
        if not center or not size:
            return None
        center_x, center_y = center
        width, height = size
        left = center_x - width / 2
        right = center_x + width / 2
        upper = center_y - height / 2
        lower = center_y + height / 2

    left = max(0, int(left))
    upper = max(0, int(upper))
    right = min(frame_width, int(right))
    lower = min(frame_height, int(lower))

    if right <= left or lower <= upper:
        return None
    return left, upper, right, lower


def _crop_frame(
    frame: Image.Image,
    rotated_bbox: Dict[str, Any],
    frame_width: int,
    frame_height: int,
) -> Optional[Image.Image]:
    """Crop frame using rotated bbox (falls back to axis-aligned)."""
    angle = rotated_bbox.get("angle") or 0.0
    if angle:
        LOGGER.warning("Rotated bbox angle=%s; using axis-aligned crop fallback.", angle)

    bbox = _axis_aligned_bbox(rotated_bbox, frame_width, frame_height)
    if not bbox:
        return None
    return frame.crop(bbox)


class CropScheduler:
    """Schedules periodic crop dispatch to classifier."""

    def __init__(
        self,
        registry: CameraRegistry,
        classifier: ClassifierClient,
        config: CropServiceConfig,
        stop_event: asyncio.Event,
        session_context=get_session_context,
    ) -> None:
        self._registry = registry
        self._classifier = classifier
        self._config = config
        self._stop_event = stop_event
        self._capture = FrameCapture(config.video_source_timeout_seconds)
        self._session_context = session_context

    async def run(self) -> None:
        while not self._stop_event.is_set():
            start_time = time.monotonic()
            await self._process_once()
            elapsed = time.monotonic() - start_time
            sleep_seconds = max(0.0, self._config.capture_interval_seconds - elapsed)
            await asyncio.sleep(sleep_seconds)

    async def _process_once(self) -> None:
        async with self._session_context() as session:
            cameras = await self._registry.list_all(session)
        for camera in cameras:
            await self._process_camera(camera)

    async def _process_camera(self, camera: CameraConfig) -> None:
        crop_json = camera.crop_json
        if not crop_json:
            LOGGER.debug("No crop JSON for camera %s", camera.camera_id)
            return

        try:
            frame = self._capture.capture(camera.video_source)
        except Exception as exc:
            LOGGER.warning("Failed to capture frame for camera %s: %s", camera.camera_id, exc)
            return

        capture_ts = datetime.utcnow()
        frame_index = crop_json.get("frame_index")
        if frame_index is None:
            frame_index = (camera.last_frame_index or 0) + 1
            crop_json["frame_index"] = frame_index
        camera.last_frame_index = frame_index

        frame_width = crop_json.get("frame_width") or frame.width
        frame_height = crop_json.get("frame_height") or frame.height
        crop_json.setdefault("frame_width", frame_width)
        crop_json.setdefault("frame_height", frame_height)

        dispatch_count = 0
        processed_count = 0
        dispatch_records: List[Dict[str, Any]] = []
        for table in crop_json.get("tables", []):
            if processed_count >= self._config.max_in_flight_per_camera:
                LOGGER.info(
                    "Camera %s reached max in-flight (%s), skipping remaining tables.",
                    camera.camera_id,
                    self._config.max_in_flight_per_camera,
                )
                break
            if not table.get("saved"):
                continue
            table_id = int(table.get("id", -1))
            if table_id < 0:
                LOGGER.warning("Invalid table id for camera %s", camera.camera_id)
                continue
            last_dispatched = (camera.last_dispatched_frame_index or {}).get(
                str(table_id)
            )
            if last_dispatched == frame_index:
                continue
            rotated_bbox = table.get("rotated_bbox")
            if not rotated_bbox:
                LOGGER.warning(
                    "Missing rotated_bbox for camera %s table %s",
                    camera.camera_id,
                    table.get("id"),
                )
                continue

            crop_image = _crop_frame(frame, rotated_bbox, frame_width, frame_height)
            if not crop_image:
                LOGGER.warning(
                    "Invalid crop bounds for camera %s table %s",
                    camera.camera_id,
                    table.get("id"),
                )
                continue

            crop_file = table.get("crop_file")
            crop_path: Path
            is_temp = False
            if crop_file:
                crop_path = Path(crop_file)
                if not crop_path.is_absolute():
                    crop_path = self._config.crops_base_dir / crop_path
                crop_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                self._config.crops_base_dir.mkdir(parents=True, exist_ok=True)
                temp_file = tempfile.NamedTemporaryFile(
                    suffix=".jpg",
                    delete=False,
                    dir=self._config.crops_base_dir,
                )
                crop_path = Path(temp_file.name)
                temp_file.close()
                is_temp = True

            crop_image.save(crop_path, format="JPEG", quality=90)
            table["crop_size"] = {"width": crop_image.width, "height": crop_image.height}

            sent = self._classifier.send_crop_with_retry(
                crop_path=crop_path,
                camera_id=camera.camera_id,
                table_id=table_id,
                frame_index=frame_index,
                video_name=crop_json.get("video_name"),
                max_attempts=self._config.dispatch_max_attempts,
                backoff_seconds=self._config.dispatch_backoff_seconds,
            )
            if is_temp and crop_path.exists():
                crop_path.unlink()
            if sent:
                dispatch_count += 1
                if camera.last_dispatched_frame_index is None:
                    camera.last_dispatched_frame_index = {}
                camera.last_dispatched_frame_index[str(table_id)] = frame_index
                dispatch_records.append(
                    {
                        "table_id": table_id,
                        "frame_index": frame_index,
                        "dispatched_at": datetime.utcnow(),
                        "status": "sent",
                    }
                )
            else:
                dispatch_records.append(
                    {
                        "table_id": table_id,
                        "frame_index": frame_index,
                        "dispatched_at": datetime.utcnow(),
                        "status": "failed",
                    }
                )
            processed_count += 1

        LOGGER.info(
            "Camera %s dispatched %s crops (frame_index=%s)",
            camera.camera_id,
            dispatch_count,
            frame_index,
        )
        async with self._session_context() as session:
            await self._registry.update_capture_state(
                session,
                camera_id=camera.camera_id,
                last_capture_ts=capture_ts,
                last_frame_index=frame_index,
                last_dispatched_frame_index=camera.last_dispatched_frame_index,
                crop_json=crop_json,
            )
            await self._registry.log_dispatches(
                session,
                camera_id=camera.camera_id,
                dispatch_records=dispatch_records,
            )


class CropService:
    """Main crop service orchestrating camera management and dispatch."""

    def __init__(self, config: CropServiceConfig) -> None:
        self._config = config
        self._registry = CameraRegistry()
        self._classifier = ClassifierClient(
            config.classifier_endpoint,
            timeout_seconds=config.classifier_timeout_seconds,
        )
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._scheduler = CropScheduler(
            registry=self._registry,
            classifier=self._classifier,
            config=config,
            stop_event=self._stop_event,
            session_context=get_session_context,
        )

    @classmethod
    def from_env(cls) -> "CropService":
        """Create service from environment variables."""
        base_dir = Path(os.getenv("CROPS_BASE_DIR", Path.cwd()))
        config = CropServiceConfig(
            classifier_endpoint=os.getenv(
                "CLASSIFIER_ENDPOINT", "http://localhost:8000/ml/predict"
            ),
            classifier_timeout_seconds=int(os.getenv("CLASSIFIER_TIMEOUT_SECONDS", "10")),
            capture_interval_seconds=int(os.getenv("CAPTURE_INTERVAL_SECONDS", "5")),
            crops_base_dir=base_dir,
            video_source_timeout_seconds=int(os.getenv("VIDEO_SOURCE_TIMEOUT_SECONDS", "5")),
            max_in_flight_per_camera=int(os.getenv("MAX_IN_FLIGHT_PER_CAMERA", "32")),
            dispatch_max_attempts=int(os.getenv("DISPATCH_MAX_ATTEMPTS", "3")),
            dispatch_backoff_seconds=float(os.getenv("DISPATCH_BACKOFF_SECONDS", "0.5")),
            refresh_command=os.getenv("CROP_REFRESH_COMMAND", ""),
            refresh_timeout_seconds=int(os.getenv("CROP_REFRESH_TIMEOUT_SECONDS", "10")),
        )
        return cls(config)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._scheduler.run())
        LOGGER.info("Crop service scheduler started.")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            await self._task
        LOGGER.info("Crop service scheduler stopped.")

    async def register_camera(
        self, camera_id: str, video_source: str, crop_json: Optional[Dict[str, Any]]
    ) -> CameraConfig:
        async with get_session_context() as session:
            return await self._registry.register(
                session=session,
                camera_id=camera_id,
                video_source=video_source,
                crop_json=crop_json,
            )

    async def update_crop_json(
        self, camera_id: str, crop_json: Dict[str, Any]
    ) -> CameraConfig:
        async with get_session_context() as session:
            return await self._registry.update_crop_json(
                session=session,
                camera_id=camera_id,
                crop_json=crop_json,
            )

    async def list_cameras(self) -> List[CameraConfig]:
        async with get_session_context() as session:
            return await self._registry.list_all(session)

    async def refresh_crop_json(self, camera_id: str) -> None:
        async with get_session_context() as session:
            camera = await self._registry.get(session, camera_id)
        if not self._config.refresh_command:
            LOGGER.info(
                "Refresh crop JSON requested for camera %s (no command configured).",
                camera.camera_id,
            )
            return

        args = [
            arg.format(camera_id=camera.camera_id)
            for arg in shlex.split(self._config.refresh_command)
        ]
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self._config.refresh_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning("Refresh command timed out for camera %s", camera.camera_id)
            return

        if result.returncode != 0:
            LOGGER.warning(
                "Refresh command failed for camera %s: %s",
                camera.camera_id,
                result.stderr.strip(),
            )
        else:
            LOGGER.info("Refresh command completed for camera %s", camera.camera_id)
