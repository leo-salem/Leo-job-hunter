from __future__ import annotations

import asyncio

from app.celery_app import celery
from app.logging_setup import configure_logging, get_logger
from app.pipeline.orchestrator import run_daily

log = get_logger(__name__)


@celery.task(
    name="app.tasks.daily.daily_scrape",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
    max_retries=3,
)
def daily_scrape(self) -> dict:
    """Full pipeline: scrape every active company, filter, dedupe, score locally."""
    configure_logging()
    log.info("daily_task_starting", attempt=self.request.retries + 1)
    result = asyncio.run(run_daily())
    summary = {
        "companies": len(result.companies),
        "new": result.total_new,
        "updated": result.total_updated,
        "closed": result.total_closed,
        "failed": result.total_failed,
    }
    log.info("daily_task_complete", **summary)
    return summary
