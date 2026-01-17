"""add crop service tables

Revision ID: 20260115_1200
Revises: 
Create Date: 2026-01-15 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260115_1200"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "camera_sources",
        sa.Column("camera_id", sa.String(length=128), primary_key=True),
        sa.Column("restaurant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("video_source", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"]),
    )

    op.create_table(
        "camera_crop_state",
        sa.Column("camera_id", sa.String(length=128), primary_key=True),
        sa.Column("crop_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_capture_ts", sa.DateTime(), nullable=True),
        sa.Column("last_frame_index", sa.Integer(), nullable=True),
        sa.Column(
            "last_dispatched_frame_index",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(["camera_id"], ["camera_sources.camera_id"]),
    )

    op.create_table(
        "crop_dispatch_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("camera_id", sa.String(length=128), nullable=False),
        sa.Column("table_id", sa.Integer(), nullable=False),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["camera_sources.camera_id"]),
        sa.UniqueConstraint(
            "camera_id",
            "table_id",
            "frame_index",
            name="uq_crop_dispatch_camera_table_frame",
        ),
    )


def downgrade() -> None:
    op.drop_table("crop_dispatch_log")
    op.drop_table("camera_crop_state")
    op.drop_table("camera_sources")
