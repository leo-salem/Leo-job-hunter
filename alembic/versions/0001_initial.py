"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-11

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("careers_url", sa.String(length=500)),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source", "external_id", name="uq_companies_source_external"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False, unique=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("location", sa.String(length=500)),
        sa.Column("country", sa.String(length=120)),
        sa.Column("remote", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("employment_type", sa.String(length=120)),
        sa.Column("department", sa.String(length=200)),
        sa.Column("team", sa.String(length=200)),
        sa.Column("description_html", sa.Text()),
        sa.Column("description_text", sa.Text()),
        sa.Column("apply_url", sa.String(length=1000), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at_source", sa.DateTime(timezone=True)),
        sa.Column("lifecycle", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "application_status",
            sa.String(length=20),
            nullable=False,
            server_default="NOT_APPLIED",
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("favorite", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text()),
        sa.Column("ai_score", sa.Float()),
        sa.Column("ai_summary", sa.Text()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("raw_payload", sa.JSON()),
    )
    op.create_index("ix_jobs_lifecycle_status", "jobs", ["lifecycle", "application_status"])
    op.create_index("ix_jobs_country_remote", "jobs", ["country", "remote"])
    op.create_index("ix_jobs_ai_score", "jobs", ["ai_score"])
    op.create_index("ix_jobs_first_seen", "jobs", ["first_seen_at"])

    op.create_table(
        "ai_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
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

    op.create_table(
        "scrape_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("source", sa.String(length=40)),
        sa.Column("company_slug", sa.String(length=120)),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("jobs_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_closed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("error_kind", sa.String(length=80)),
    )
    op.create_index("ix_scrape_logs_started", "scrape_logs", ["started_at"])

    op.create_table(
        "system_state",
        sa.Column("key", sa.String(length=80), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("system_state")
    op.drop_index("ix_scrape_logs_started", table_name="scrape_logs")
    op.drop_table("scrape_logs")
    op.drop_index("ix_ai_analyses_prompt_hash", table_name="ai_analyses")
    op.drop_table("ai_analyses")
    op.drop_index("ix_jobs_first_seen", table_name="jobs")
    op.drop_index("ix_jobs_ai_score", table_name="jobs")
    op.drop_index("ix_jobs_country_remote", table_name="jobs")
    op.drop_index("ix_jobs_lifecycle_status", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("companies")
