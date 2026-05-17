"""local heuristic score on jobs

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-17

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("heuristic_score", sa.Float(), nullable=True),
    )
    op.create_index("ix_jobs_heuristic_score", "jobs", ["heuristic_score"])


def downgrade() -> None:
    op.drop_index("ix_jobs_heuristic_score", table_name="jobs")
    op.drop_column("jobs", "heuristic_score")
