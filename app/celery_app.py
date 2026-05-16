from __future__ import annotations

from celery import Celery

from app.config import settings

# NOTE: no beat schedule. Scrapes only run on user demand:
#   - start.bat  → kicks off scripts.run_once which calls run_daily()
#   - "Refresh now" button on the dashboard → POST /refresh (synchronous)
# The worker is still used by analyze_recent_jobs after a refresh completes.

celery = Celery(
    "job_hunter",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.daily", "app.tasks.scrape", "app.tasks.analyze"],
)

celery.conf.update(
    timezone=settings.timezone,
    enable_utc=False,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_max_tasks_per_child=200,
    broker_connection_retry_on_startup=True,
    result_expires=60 * 60 * 24 * 7,
)
