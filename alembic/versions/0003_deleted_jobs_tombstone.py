"""tombstone table for permanently-deleted (Submitted) jobs

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-16

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deleted_jobs",
        sa.Column("fingerprint", sa.String(length=64), primary_key=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("title", sa.String(length=500)),
        sa.Column("source", sa.String(length=40)),
    )


def downgrade() -> None:
    op.drop_table("deleted_jobs")
