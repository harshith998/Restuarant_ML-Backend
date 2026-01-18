"""
Pydantic schemas for video upload pipeline API.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VideoJobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ============== Request Schemas ==============

class VideoProcessRequest(BaseModel):
    """Request to process video frames with classification."""
    crop_json: Optional[Dict[str, Any]] = Field(
        None, description="Crop JSON with table bounding boxes"
    )
    camera_id: Optional[str] = Field(
        None, description="Use existing camera's crop JSON"
    )
    process_every_n: int = Field(
        1, ge=1, description="Process every Nth frame"
    )
    update_db: bool = Field(
        True, description="Update table states in database"
    )
    consensus_window: int = Field(
        5, ge=1, le=30, description="Number of consecutive frames needed to switch state (temporal smoothing)"
    )


# ============== Response Schemas ==============

class VideoUploadResponse(BaseModel):
    """Response after video upload."""
    job_id: UUID
    status: VideoJobStatus
    file_name: str
    file_size_bytes: int
    created_at: datetime


class VideoJobResponse(BaseModel):
    """Response with video job status and metadata."""
    model_config = ConfigDict(from_attributes=True)

    job_id: UUID = Field(alias="id")
    status: VideoJobStatus
    progress_percent: int
    frames_extracted: int

    # Video metadata
    duration_seconds: Optional[float] = None
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    codec: Optional[str] = None

    # Timestamps
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Error info
    error_message: Optional[str] = None


class ExtractedFrameResponse(BaseModel):
    """Response for a single extracted frame."""
    model_config = ConfigDict(from_attributes=True)

    frame_id: UUID = Field(alias="id")
    frame_index: int
    timestamp_ms: int
    url: str
    width: Optional[int] = None
    height: Optional[int] = None


class FrameListResponse(BaseModel):
    """Response with paginated list of extracted frames."""
    job_id: UUID
    total_frames: int
    page: int
    limit: int
    frames: List[ExtractedFrameResponse]


class TableClassificationResult(BaseModel):
    """Classification result for a single table."""
    table_id: Optional[UUID] = None
    table_number: Optional[str] = None
    state: str
    confidence: float


class FrameClassificationResult(BaseModel):
    """Classification results for all tables in a frame."""
    frame_index: int
    timestamp_ms: int
    tables: List[TableClassificationResult]


class TableStateSummary(BaseModel):
    """Summary of state changes for a single table."""
    final_state: str
    final_smoothed_state: Optional[str] = None
    state_changes: List[Dict[str, Any]]
    smoothed_state_changes: Optional[List[Dict[str, Any]]] = None


class VideoProcessResponse(BaseModel):
    """Response after starting video processing."""
    job_id: UUID
    process_task_id: UUID
    status: str
    frames_to_process: int
    tables_count: int


class VideoResultsResponse(BaseModel):
    """Response with classification results."""
    job_id: UUID
    status: VideoJobStatus
    frames_processed: int
    tables_updated: int
    summary: Dict[str, TableStateSummary]
    per_frame_results: Optional[List[FrameClassificationResult]] = None


# ============== Internal Schemas ==============

class VideoMetadata(BaseModel):
    """Video metadata extracted via ffprobe."""
    duration_seconds: float
    fps: float
    width: int
    height: int
    codec: str


class FrameExtractionResult(BaseModel):
    """Result of frame extraction."""
    frame_count: int
    frame_paths: List[str]
    output_dir: str
