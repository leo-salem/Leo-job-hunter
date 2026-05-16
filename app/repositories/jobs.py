from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ApplicationStatus, DeletedJob, Job, JobLifecycle, Region, Source
from app.utils.time import now_utc


async def get_by_fingerprint(session: AsyncSession, fp: str) -> Job | None:
    stmt = select(Job).where(Job.fingerprint == fp)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_by_id(session: AsyncSession, job_id: int) -> Job | None:
    stmt = select(Job).options(selectinload(Job.company)).where(Job.id == job_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def fingerprints_for_company(session: AsyncSession, company_id: int) -> set[str]:
    stmt = select(Job.fingerprint).where(
        Job.company_id == company_id,
        Job.lifecycle == JobLifecycle.ACTIVE,
    )
    return {row[0] for row in (await session.execute(stmt)).all()}


async def mark_closed(session: AsyncSession, job_ids: Sequence[int]) -> int:
    if not job_ids:
        return 0
    stmt = (
        update(Job)
        .where(Job.id.in_(list(job_ids)), Job.lifecycle == JobLifecycle.ACTIVE)
        .values(lifecycle=JobLifecycle.CLOSED, closed_at=now_utc())
    )
    res = await session.execute(stmt)
    return res.rowcount or 0


async def ids_to_close_for_company(
    session: AsyncSession, company_id: int, seen_fingerprints: set[str]
) -> list[int]:
    stmt = select(Job.id, Job.fingerprint).where(
        Job.company_id == company_id, Job.lifecycle == JobLifecycle.ACTIVE
    )
    rows = (await session.execute(stmt)).all()
    return [r.id for r in rows if r.fingerprint not in seen_fingerprints]


async def update_last_seen(session: AsyncSession, job_ids: Sequence[int]) -> None:
    if not job_ids:
        return
    stmt = (
        update(Job).where(Job.id.in_(list(job_ids))).values(last_seen_at=now_utc())
    )
    await session.execute(stmt)


async def search_jobs(
    session: AsyncSession,
    *,
    lifecycles: list[JobLifecycle] | None = None,
    statuses: list[ApplicationStatus] | None = None,
    sources: list[Source] | None = None,
    countries: list[str] | None = None,
    region: Region | None = None,
    remote_only: bool = False,
    favorites_only: bool = False,
    min_score: float | None = None,
    query: str | None = None,
    limit: int = 200,
    offset: int = 0,
    order_by: str = "score",
) -> list[Job]:
    stmt = select(Job).options(selectinload(Job.company))
    conditions = []
    if region is not None:
        conditions.append(Job.region == region)
    if lifecycles:
        conditions.append(Job.lifecycle.in_(lifecycles))
    if statuses:
        conditions.append(Job.application_status.in_(statuses))
    if sources:
        conditions.append(Job.source.in_(sources))
    if countries:
        conditions.append(Job.country.in_(countries))
    if remote_only:
        conditions.append(Job.remote.is_(True))
    if favorites_only:
        conditions.append(Job.favorite.is_(True))
    if min_score is not None:
        conditions.append(Job.ai_score >= min_score)
    if query:
        like = f"%{query.lower()}%"
        conditions.append(
            or_(func.lower(Job.title).like(like), func.lower(Job.description_text).like(like))
        )
    if conditions:
        stmt = stmt.where(and_(*conditions))

    if order_by == "score":
        stmt = stmt.order_by(Job.ai_score.desc().nullslast(), Job.first_seen_at.desc())
    elif order_by == "newest":
        stmt = stmt.order_by(Job.first_seen_at.desc())
    elif order_by == "company":
        stmt = stmt.order_by(Job.company_id, Job.first_seen_at.desc())

    stmt = stmt.limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars())


async def count_by_status(session: AsyncSession) -> dict[str, int]:
    stmt = select(Job.application_status, func.count()).group_by(Job.application_status)
    rows = (await session.execute(stmt)).all()
    return {r[0].value if hasattr(r[0], "value") else str(r[0]): r[1] for r in rows}


async def set_application_status(
    session: AsyncSession, job_id: int, status: ApplicationStatus
) -> Job | None:
    job = await get_by_id(session, job_id)
    if job is None:
        return None
    job.application_status = status
    if status == ApplicationStatus.APPLIED and job.applied_at is None:
        job.applied_at = now_utc()
    return job


async def toggle_favorite(session: AsyncSession, job_id: int) -> Job | None:
    job = await get_by_id(session, job_id)
    if job is None:
        return None
    job.favorite = not job.favorite
    return job


async def archive(session: AsyncSession, job_id: int) -> Job | None:
    job = await get_by_id(session, job_id)
    if job is None:
        return None
    job.lifecycle = JobLifecycle.ARCHIVED
    return job


async def set_notes(session: AsyncSession, job_id: int, notes: str | None) -> Job | None:
    job = await get_by_id(session, job_id)
    if job is None:
        return None
    job.notes = notes
    return job


async def delete_job(session: AsyncSession, job_id: int) -> bool:
    """Hard-delete the job AND tombstone its fingerprint so the next scrape
    won't re-insert it. Returns True if a row was actually removed."""
    job = await get_by_id(session, job_id)
    if job is None:
        return False
    tombstone = DeletedJob(
        fingerprint=job.fingerprint,
        title=job.title,
        source=job.source.value if hasattr(job.source, "value") else str(job.source),
    )
    session.add(tombstone)
    await session.flush()  # write tombstone first so cascade delete works
    await session.delete(job)
    return True


async def is_tombstoned(session: AsyncSession, fingerprint: str) -> bool:
    row = await session.get(DeletedJob, fingerprint)
    return row is not None


async def tombstoned_fingerprints(session: AsyncSession) -> set[str]:
    stmt = select(DeletedJob.fingerprint)
    return {row[0] for row in (await session.execute(stmt)).all()}
