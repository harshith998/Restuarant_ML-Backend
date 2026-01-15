from __future__ import annotations

import asyncio
import io
import json
import logging
import mimetypes
import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import request

from PIL import Image

LOGGER = logging.getLogger("crop-service")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


@dataclass
class CropServiceConfig:
    classifier_endpoint: str
    classifier_timeout_seconds: int
    capture_interval_seconds: int
    crops_base_dir: Path
    state_path: Path
    video_source_timeout_seconds: int
    max_in_flight_per_camera: int
    dispatch_max_attempts: int
    dispatch_backoff_seconds: float


@dataclass
class CameraConfig:
    camera_id: str
    video_source: str
    crop_json: Optional[Dict[str, Any]] = None
    last_capture_ts: float = 0.0
    last_frame_index: Optional[int] = None


class JsonStateStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Dict[str, Any]:
        if not self._path.exists():
            return {"cameras": {}}
        with self._path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, data: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)


class CameraRegistry:
    def __init__(self, store: JsonStateStore) -> None:
        self._store = store
        self._cameras: Dict[str, CameraConfig] = {}

    def load(self) -> None:
        payload = self._store.load()
        cameras = payload.get("cameras", {})
        for camera_id, data in cameras.items():
            self._cameras[camera_id] = CameraConfig(
                camera_id=camera_id,
                video_source=data["video_source"],
                crop_json=data.get("crop_json"),
                last_capture_ts=data.get("last_capture_ts", 0.0),
                last_frame_index=data.get("last_frame_index"),
            )

    def save(self) -> None:
        payload = {
            "cameras": {
                camera_id: {
                    "video_source": cam.video_source,
                    "crop_json": cam.crop_json,
                    "last_capture_ts": cam.last_capture_ts,
                    "last_frame_index": cam.last_frame_index,
                }
                for camera_id, cam in self._cameras.items()
            }
        }
        self._store.save(payload)

    def register(self, camera_id: str, video_source: str, crop_json: Optional[Dict[str, Any]]) -> CameraConfig:
        camera = CameraConfig(camera_id=camera_id, video_source=video_source, crop_json=crop_json)
        self._cameras[camera_id] = camera
        self.save()
        return camera

    def update_crop_json(self, camera_id: str, crop_json: Dict[str, Any]) -> CameraConfig:
        camera = self.get(camera_id)
        camera.crop_json = crop_json
        camera.last_frame_index = crop_json.get("frame_index")
        self.save()
        return camera

    def get(self, camera_id: str) -> CameraConfig:
        if camera_id not in self._cameras:
            raise KeyError(f"Camera '{camera_id}' not registered.")
        return self._cameras[camera_id]

    def list_all(self) -> List[CameraConfig]:
        return list(self._cameras.values())


class ClassifierClient:
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
        body, boundary = _encode_multipart(fields, ("file", crop_path.name, content_type, file_bytes))
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
    file_part: tuple[str, str, str, bytes],
) -> tuple[bytes, str]:
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
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'.encode("utf-8")
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
    angle = rotated_bbox.get("angle") or 0.0
    if angle:
        LOGGER.warning("Rotated bbox angle=%s; using axis-aligned crop fallback.", angle)

    bbox = _axis_aligned_bbox(rotated_bbox, frame_width, frame_height)
    if not bbox:
        return None
    return frame.crop(bbox)


class CropScheduler:
    def __init__(
        self,
        registry: CameraRegistry,
        classifier: ClassifierClient,
        config: CropServiceConfig,
        stop_event: asyncio.Event,
    ) -> None:
        self._registry = registry
        self._classifier = classifier
        self._config = config
        self._stop_event = stop_event
        self._capture = FrameCapture(config.video_source_timeout_seconds)

    async def run(self) -> None:
        while not self._stop_event.is_set():
            start_time = time.monotonic()
            await self._process_once()
            elapsed = time.monotonic() - start_time
            sleep_seconds = max(0.0, self._config.capture_interval_seconds - elapsed)
            await asyncio.sleep(sleep_seconds)

    async def _process_once(self) -> None:
        for camera in self._registry.list_all():
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

        camera.last_capture_ts = time.time()
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
            rotated_bbox = table.get("rotated_bbox")
            if not rotated_bbox:
                LOGGER.warning("Missing rotated_bbox for camera %s table %s", camera.camera_id, table.get("id"))
                continue

            crop_image = _crop_frame(frame, rotated_bbox, frame_width, frame_height)
            if not crop_image:
                LOGGER.warning("Invalid crop bounds for camera %s table %s", camera.camera_id, table.get("id"))
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
                table_id=int(table.get("id", -1)),
                frame_index=frame_index,
                video_name=crop_json.get("video_name"),
                max_attempts=self._config.dispatch_max_attempts,
                backoff_seconds=self._config.dispatch_backoff_seconds,
            )
            if is_temp and crop_path.exists():
                crop_path.unlink()
            if sent:
                dispatch_count += 1
            processed_count += 1

        LOGGER.info(
            "Camera %s dispatched %s crops (frame_index=%s)",
            camera.camera_id,
            dispatch_count,
            frame_index,
        )
        self._registry.save()


class CropService:
    def __init__(self, config: CropServiceConfig) -> None:
        self._config = config
        self._store = JsonStateStore(config.state_path)
        self._registry = CameraRegistry(self._store)
        self._classifier = ClassifierClient(
            config.classifier_endpoint,
            timeout_seconds=config.classifier_timeout_seconds,
        )
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        self._scheduler = CropScheduler(
            registry=self._registry,
            classifier=self._classifier,
            config=config,
            stop_event=self._stop_event,
        )

    @classmethod
    def from_env(cls) -> "CropService":
        base_dir = Path(os.getenv("CROPS_BASE_DIR", Path.cwd()))
        state_path = Path(os.getenv("CROP_SERVICE_STATE", "data/crop_service_state.json"))
        config = CropServiceConfig(
            classifier_endpoint=os.getenv("CLASSIFIER_ENDPOINT", "http://localhost:8000/predict"),
            classifier_timeout_seconds=int(os.getenv("CLASSIFIER_TIMEOUT_SECONDS", "10")),
            capture_interval_seconds=int(os.getenv("CAPTURE_INTERVAL_SECONDS", "5")),
            crops_base_dir=base_dir,
            state_path=state_path,
            video_source_timeout_seconds=int(os.getenv("VIDEO_SOURCE_TIMEOUT_SECONDS", "5")),
            max_in_flight_per_camera=int(os.getenv("MAX_IN_FLIGHT_PER_CAMERA", "32")),
            dispatch_max_attempts=int(os.getenv("DISPATCH_MAX_ATTEMPTS", "3")),
            dispatch_backoff_seconds=float(os.getenv("DISPATCH_BACKOFF_SECONDS", "0.5")),
        )
        return cls(config)

    async def start(self) -> None:
        self._registry.load()
        self._task = asyncio.create_task(self._scheduler.run())
        LOGGER.info("Crop service scheduler started.")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            await self._task
        LOGGER.info("Crop service scheduler stopped.")

    def register_camera(self, camera_id: str, video_source: str, crop_json: Optional[Dict[str, Any]]) -> CameraConfig:
        return self._registry.register(camera_id=camera_id, video_source=video_source, crop_json=crop_json)

    def update_crop_json(self, camera_id: str, crop_json: Dict[str, Any]) -> CameraConfig:
        return self._registry.update_crop_json(camera_id=camera_id, crop_json=crop_json)

    def list_cameras(self) -> List[CameraConfig]:
        return self._registry.list_all()

    def refresh_crop_json(self, camera_id: str) -> None:
        camera = self._registry.get(camera_id)
        LOGGER.info("Refresh crop JSON requested for camera %s (stub).", camera.camera_id)
