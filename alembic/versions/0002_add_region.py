"""add region to companies and jobs + register new sources

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-12

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "target_region",
            sa.String(length=20),
            nullable=False,
            server_default="INTERNATIONAL",
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "region",
            sa.String(length=20),
            nullable=False,
            server_default="INTERNATIONAL",
        ),
    )
    op.create_index(
        "ix_jobs_region_lifecycle_status",
        "jobs",
        ["region", "lifecycle", "application_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_region_lifecycle_status", table_name="jobs")
    op.drop_column("jobs", "region")
    op.drop_column("companies", "target_region")
