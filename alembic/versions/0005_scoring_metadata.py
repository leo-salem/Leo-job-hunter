"""add confidence + score_breakdown to jobs

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-17

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("heuristic_confidence", sa.Float(), nullable=True))
    op.add_column("jobs", sa.Column("score_breakdown", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "score_breakdown")
    op.drop_column("jobs", "heuristic_confidence")
