from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import JSON

from app.database import Base

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class CameraSource(Base):
    """Registered camera sources for crop ingestion."""

    __tablename__ = "camera_sources"

    camera_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    restaurant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=True
    )
    video_source: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    crop_state: Mapped[Optional["CameraCropState"]] = relationship(
        "CameraCropState", back_populates="camera", uselist=False, cascade="all, delete-orphan"
    )
    dispatch_logs: Mapped[list["CropDispatchLog"]] = relationship(
        "CropDispatchLog", back_populates="camera", cascade="all, delete-orphan"
    )


class CameraCropState(Base):
    """Latest crop JSON and capture metadata for a camera."""

    __tablename__ = "camera_crop_state"

    camera_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("camera_sources.camera_id"), primary_key=True
    )
    crop_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON_TYPE, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    last_capture_ts: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_frame_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_dispatched_frame_index: Mapped[Dict[str, int]] = mapped_column(
        JSON_TYPE, default=dict
    )

    camera: Mapped["CameraSource"] = relationship(
        "CameraSource", back_populates="crop_state"
    )


class CropDispatchLog(Base):
    """Audit log for crop dispatch attempts."""

    __tablename__ = "crop_dispatch_log"
    __table_args__ = (
        UniqueConstraint(
            "camera_id",
            "table_id",
            "frame_index",
            name="uq_crop_dispatch_camera_table_frame",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    camera_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("camera_sources.camera_id"), nullable=False
    )
    table_id: Mapped[int] = mapped_column(Integer, nullable=False)
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    camera: Mapped["CameraSource"] = relationship(
        "CameraSource", back_populates="dispatch_logs"
    )
