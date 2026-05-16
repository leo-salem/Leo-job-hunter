from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.celery_app import celery
from app.config import settings
from app.db.models import ApplicationStatus, Job, JobLifecycle
from app.db.session import session_scope
from app.logging_setup import configure_logging, get_logger

log = get_logger(__name__)


@celery.task(name="app.tasks.analyze.analyze_recent_jobs", autoretry_for=(Exception,), max_retries=1)
def analyze_recent_jobs() -> dict:
    configure_logging()
    if not settings.ai_ready:
        log.info("ai_disabled_skip_analysis")
        return {"status": "skipped", "reason": "ai_disabled"}
    return asyncio.run(_analyze_recent())


async def _analyze_recent() -> dict:
    from app.ai.analyzer import score_job

    async with session_scope() as session:
        stmt = (
            select(Job)
            .where(
                Job.lifecycle == JobLifecycle.ACTIVE,
                Job.application_status == ApplicationStatus.NOT_APPLIED,
                Job.ai_score.is_(None),
            )
            .order_by(Job.first_seen_at.desc())
            .limit(settings.ai_max_jobs_per_run)
        )
        jobs = list((await session.execute(stmt)).scalars())

    log.info("analyze_batch_starting", count=len(jobs))
    succeeded = 0
    failed = 0
    for job in jobs:
        try:
            await score_job(job.id)
            succeeded += 1
        except Exception:  # noqa: BLE001
            log.exception("analyze_failed", job_id=job.id)
            failed += 1
    log.info("analyze_batch_done", succeeded=succeeded, failed=failed)
    return {"status": "ok", "succeeded": succeeded, "failed": failed}


@celery.task(name="app.tasks.analyze.analyze_one", autoretry_for=(Exception,), max_retries=1)
def analyze_one(job_id: int) -> dict:
    configure_logging()
    if not settings.ai_ready:
        return {"status": "skipped"}
    from app.ai.analyzer import score_job

    return asyncio.run(score_job(job_id))
