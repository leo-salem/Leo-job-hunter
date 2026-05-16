from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class JobLifecycle(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"      # disappeared from source
    ARCHIVED = "ARCHIVED"  # manually archived


class ApplicationStatus(str, enum.Enum):
    NOT_APPLIED = "NOT_APPLIED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    INTERVIEWING = "INTERVIEWING"
    OFFER = "OFFER"


class Source(str, enum.Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKDAY = "workday"
    WELLFOUND = "wellfound"
    LINKEDIN = "linkedin"
    WUZZUF = "wuzzuf"
    BAYT = "bayt"


class Region(str, enum.Enum):
    INTERNATIONAL = "INTERNATIONAL"   # USA + Europe + Remote (existing flow)
    EGYPT = "EGYPT"                   # Egypt-targeted (LinkedIn + Wuzzuf + Egypt-located roles)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[Source] = mapped_column(SAEnum(Source, native_enum=False), nullable=False)
    # Source-specific identifier (e.g. greenhouse board token, lever org slug, ashby org slug)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    careers_url: Mapped[Optional[str]] = mapped_column(String(500))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    target_region: Mapped[Region] = mapped_column(
        SAEnum(Region, native_enum=False),
        default=Region.INTERNATIONAL,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    jobs: Mapped[list["Job"]] = relationship(back_populates="company")

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_companies_source_external"),
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)

    # Stable, sha256-hex deduplication key derived from (source, external_id) or (source, url)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    source: Mapped[Source] = mapped_column(SAEnum(Source, native_enum=False), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(500))
    country: Mapped[Optional[str]] = mapped_column(String(120))  # normalized
    remote: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    employment_type: Mapped[Optional[str]] = mapped_column(String(120))
    department: Mapped[Optional[str]] = mapped_column(String(200))
    team: Mapped[Optional[str]] = mapped_column(String(200))

    description_html: Mapped[Optional[str]] = mapped_column(Text)
    description_text: Mapped[Optional[str]] = mapped_column(Text)
    apply_url: Mapped[str] = mapped_column(String(1000), nullable=False)

    region: Mapped[Region] = mapped_column(
        SAEnum(Region, native_enum=False),
        default=Region.INTERNATIONAL,
        nullable=False,
    )

    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at_source: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Lifecycle
    lifecycle: Mapped[JobLifecycle] = mapped_column(
        SAEnum(JobLifecycle, native_enum=False),
        default=JobLifecycle.ACTIVE,
        nullable=False,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # User-controlled
    application_status: Mapped[ApplicationStatus] = mapped_column(
        SAEnum(ApplicationStatus, native_enum=False),
        default=ApplicationStatus.NOT_APPLIED,
        nullable=False,
    )
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # AI
    ai_score: Mapped[Optional[float]] = mapped_column(Float)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)

    # Internal
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON)

    company: Mapped[Company] = relationship(back_populates="jobs")
    ai_analyses: Mapped[list["AIAnalysis"]] = relationship(back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_jobs_lifecycle_status", "lifecycle", "application_status"),
        Index("ix_jobs_country_remote", "country", "remote"),
        Index("ix_jobs_ai_score", "ai_score"),
        Index("ix_jobs_first_seen", "first_seen_at"),
        Index("ix_jobs_region_lifecycle_status", "region", "lifecycle", "application_status"),
    )


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # score | cover_letter | resume_summary
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[Optional[float]] = mapped_column(Float)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped[Job] = relationship(back_populates="ai_analyses")

    __table_args__ = (
        UniqueConstraint("job_id", "kind", "prompt_hash", name="uq_ai_analyses_job_kind_hash"),
    )


class ScrapeLog(Base):
    __tablename__ = "scrape_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source: Mapped[Optional[Source]] = mapped_column(SAEnum(Source, native_enum=False))
    company_slug: Mapped[Optional[str]] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), nullable=False)  # ok | failed | partial
    jobs_seen: Mapped[int] = mapped_column(Integer, default=0)
    jobs_new: Mapped[int] = mapped_column(Integer, default=0)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0)
    jobs_closed: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_kind: Mapped[Optional[str]] = mapped_column(String(80))

    __table_args__ = (Index("ix_scrape_logs_started", "started_at"),)


class SystemState(Base):
    """Key/value store for catchup tracking and similar app-level state."""

    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DeletedJob(Base):
    """Tombstone for jobs the user permanently deleted via 'Submitted'.

    The scraper checks this table before inserting — fingerprints listed here
    are never re-added, even if the source page still lists the job.
    """

    __tablename__ = "deleted_jobs"

    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    title: Mapped[Optional[str]] = mapped_column(String(500))
    source: Mapped[Optional[str]] = mapped_column(String(40))


# Common keys for SystemState
KEY_LAST_SUCCESSFUL_DAILY = "last_successful_daily_run"
