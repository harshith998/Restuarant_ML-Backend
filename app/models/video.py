"""
Video processing models for upload pipeline.

VideoJob: Tracks video upload and frame extraction jobs
ExtractedFrame: Individual frames extracted from videos
FrameClassification: Classification results for table crops per frame
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import uuid

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant
    from app.models.table import Table


class VideoJob(Base):
    """Video processing job tracking."""

    __tablename__ = "video_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    restaurant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=True
    )
    camera_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # File info
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Video metadata (populated after probe)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    fps: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    codec: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Job status
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    frames_extracted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Relationships
    restaurant: Mapped[Optional["Restaurant"]] = relationship("Restaurant")
    frames: Mapped[List["ExtractedFrame"]] = relationship(
        "ExtractedFrame", back_populates="job", cascade="all, delete-orphan"
    )
    classifications: Mapped[List["FrameClassification"]] = relationship(
        "FrameClassification", back_populates="job", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_video_jobs_status", "status"),
        Index("idx_video_jobs_restaurant", "restaurant_id"),
    )

    def __repr__(self) -> str:
        return f"<VideoJob(id={self.id}, status={self.status}, frames={self.frames_extracted})>"


class ExtractedFrame(Base):
    """Individual frame extracted from a video."""

    __tablename__ = "extracted_frames"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("video_jobs.id", ondelete="CASCADE"), nullable=False
    )
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    job: Mapped["VideoJob"] = relationship("VideoJob", back_populates="frames")

    __table_args__ = (
        Index("idx_extracted_frames_job", "job_id"),
        Index("idx_extracted_frames_job_index", "job_id", "frame_index", unique=True),
    )

    def __repr__(self) -> str:
        return f"<ExtractedFrame(job_id={self.job_id}, index={self.frame_index})>"


class FrameClassification(Base):
    """Classification result for a table crop in a frame."""

    __tablename__ = "frame_classifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("video_jobs.id", ondelete="CASCADE"), nullable=False
    )
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    table_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tables.id"), nullable=True
    )
    table_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    predicted_state: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    # Smoothed state after N-frame consensus (may differ from predicted_state)
    smoothed_state: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    job: Mapped["VideoJob"] = relationship("VideoJob", back_populates="classifications")
    table: Mapped[Optional["Table"]] = relationship("Table")

    __table_args__ = (
        Index("idx_frame_classifications_job", "job_id"),
        Index("idx_frame_classifications_job_frame", "job_id", "frame_index"),
    )

    def __repr__(self) -> str:
        return f"<FrameClassification(job_id={self.job_id}, frame={self.frame_index}, table={self.table_number}, state={self.predicted_state})>"
