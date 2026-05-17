"""drop AI columns and ai_analyses table

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-17

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_jobs_ai_score", table_name="jobs")
    op.drop_column("jobs", "ai_summary")
    op.drop_column("jobs", "ai_score")
    op.drop_index("ix_ai_analyses_prompt_hash", table_name="ai_analyses")
    op.drop_table("ai_analyses")


def downgrade() -> None:
    op.add_column("jobs", sa.Column("ai_score", sa.Float(), nullable=True))
    op.add_column("jobs", sa.Column("ai_summary", sa.Text(), nullable=True))
    op.create_index("ix_jobs_ai_score", "jobs", ["ai_score"])
    op.create_table(
        "ai_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("score", sa.Float()),
        sa.Column("extra", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("job_id", "kind", "prompt_hash", name="uq_ai_analyses_job_kind_hash"),
    )
    op.create_index("ix_ai_analyses_prompt_hash", "ai_analyses", ["prompt_hash"])
