"""Manual one-shot trigger of the daily pipeline (without going through Celery)."""
from __future__ import annotations

import asyncio

from app.logging_setup import configure_logging, get_logger
from app.pipeline.orchestrator import run_daily

log = get_logger(__name__)


async def main() -> None:
    configure_logging()
    result = await run_daily()
    log.info(
        "run_once_done",
        new_jobs=result.total_new,
        failed_companies=result.total_failed,
        per_company=[
            {
                "company": c.company_slug,
                "status": c.status,
                "new": c.new,
                "updated": c.updated,
                "closed": c.closed,
                "error": c.error,
            }
            for c in result.companies
        ],
    )


if __name__ == "__main__":
    asyncio.run(main())
