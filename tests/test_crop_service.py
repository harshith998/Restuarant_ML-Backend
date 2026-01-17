from datetime import datetime

import pytest
from PIL import Image
from sqlalchemy import select

from app.ml.crop_service import CameraRegistry, _axis_aligned_bbox, _crop_frame
from app.models.crop import CropDispatchLog


def test_axis_aligned_bbox_from_corners() -> None:
    rotated_bbox = {"corners": [[10, 10], [90, 10], [90, 80], [10, 80]]}
    bbox = _axis_aligned_bbox(rotated_bbox, frame_width=100, frame_height=100)
    assert bbox == (10, 10, 90, 80)


def test_crop_frame_clamps_out_of_bounds() -> None:
    frame = Image.new("RGB", (100, 100), color="white")
    rotated_bbox = {"corners": [[-10, -10], [50, -10], [50, 120], [-10, 120]]}
    crop = _crop_frame(frame, rotated_bbox, frame_width=100, frame_height=100)
    assert crop is not None
    assert crop.size == (50, 100)


@pytest.mark.asyncio
async def test_registry_roundtrip(db_session) -> None:
    registry = CameraRegistry()
    await registry.register(db_session, "cam-1", "/tmp/video.jpg", {"frame_index": 1})
    await registry.update_crop_json(db_session, "cam-1", {"frame_index": 2})

    camera = await registry.get(db_session, "cam-1")
    assert camera.video_source == "/tmp/video.jpg"
    assert camera.crop_json == {"frame_index": 2}
    assert camera.last_frame_index == 2


@pytest.mark.asyncio
async def test_dispatch_log_persistence(db_session) -> None:
    registry = CameraRegistry()
    await registry.register(db_session, "cam-2", "/tmp/video.jpg", {"frame_index": 1})

    await registry.update_capture_state(
        db_session,
        camera_id="cam-2",
        last_capture_ts=datetime.utcnow(),
        last_frame_index=3,
        last_dispatched_frame_index={"1": 3},
        crop_json={"frame_index": 3},
    )
    await registry.log_dispatches(
        db_session,
        camera_id="cam-2",
        dispatch_records=[
            {
                "table_id": 1,
                "frame_index": 3,
                "dispatched_at": datetime.utcnow(),
                "status": "sent",
            }
        ],
    )

    result = await db_session.execute(select(CropDispatchLog))
    logs = result.scalars().all()
    assert len(logs) == 1
    assert logs[0].camera_id == "cam-2"
