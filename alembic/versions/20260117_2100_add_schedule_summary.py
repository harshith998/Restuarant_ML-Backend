"""add_schedule_summary

Revision ID: 9f3a4b2d7c11
Revises: 885e2489fc5a
Create Date: 2026-01-17 21:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f3a4b2d7c11"
down_revision: Union[str, None] = "885e2489fc5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("schedules", sa.Column("schedule_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("schedules", "schedule_summary")
