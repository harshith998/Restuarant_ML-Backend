"""add video pipeline tables

Revision ID: 20260117_1000
Revises: 20260115_1200
Create Date: 2026-01-17 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260117_1000"
down_revision = "20260115_1200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Video Jobs table
    op.create_table(
        "video_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("camera_id", sa.String(length=100), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=512), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("fps", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("codec", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("frames_extracted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"]),
    )
    op.create_index("idx_video_jobs_status", "video_jobs", ["status"])
    op.create_index("idx_video_jobs_restaurant", "video_jobs", ["restaurant_id"])

    # Extracted Frames table
    op.create_table(
        "extracted_frames",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("timestamp_ms", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["video_jobs.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_extracted_frames_job", "extracted_frames", ["job_id"])
    op.create_index(
        "idx_extracted_frames_job_index",
        "extracted_frames",
        ["job_id", "frame_index"],
        unique=True,
    )

    # Frame Classifications table
    op.create_table(
        "frame_classifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("table_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("table_number", sa.String(length=20), nullable=True),
        sa.Column("predicted_state", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["video_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["table_id"], ["tables.id"]),
    )
    op.create_index("idx_frame_classifications_job", "frame_classifications", ["job_id"])
    op.create_index(
        "idx_frame_classifications_job_frame",
        "frame_classifications",
        ["job_id", "frame_index"],
    )


def downgrade() -> None:
    op.drop_table("frame_classifications")
    op.drop_table("extracted_frames")
    op.drop_table("video_jobs")
