"""Run the daily pipeline if the last successful run is stale.

Called automatically on FastAPI startup; can also be invoked manually:

    docker compose run --rm api python -m scripts.catchup
"""
from __future__ import annotations

import asyncio

from app.config import settings
from app.db.session import session_scope
from app.logging_setup import configure_logging, get_logger
from app.pipeline.orchestrator import run_daily
from app.repositories import companies as companies_repo
from app.repositories import scrape_logs as scrape_logs_repo
from app.utils.time import now_utc

log = get_logger(__name__)


async def is_catchup_needed() -> bool:
    """True when either:
      - no successful daily run is recorded yet, OR
      - the last successful daily was longer ago than CATCHUP_THRESHOLD_HOURS.

    Refuses to say "needed" if there are zero seeded companies — otherwise an
    empty run would mark itself successful and suppress future catchups.
    """
    async with session_scope() as session:
        companies = await companies_repo.list_active(session)
        if not companies:
            log.warning("catchup_skipped_no_companies")
            return False
        last = await scrape_logs_repo.get_last_successful_daily(session)
    if last is None:
        return True
    delta = now_utc() - last
    return delta.total_seconds() >= settings.catchup_threshold_hours * 3600


async def maybe_run_catchup() -> dict:
    needed = await is_catchup_needed()
    if not needed:
        log.info("catchup_not_needed")
        return {"ran": False}
    log.info("catchup_running")
    result = await run_daily()
    return {
        "ran": True,
        "new": result.total_new,
        "updated": result.total_updated,
        "closed": result.total_closed,
        "failed": result.total_failed,
    }


if __name__ == "__main__":
    configure_logging()
    out = asyncio.run(maybe_run_catchup())
    log.info("catchup_finished", **out)
