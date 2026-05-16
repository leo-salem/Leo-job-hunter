from __future__ import annotations

import asyncio

from app.celery_app import celery
from app.db.models import Source
from app.db.session import session_scope
from app.logging_setup import configure_logging, get_logger
from app.pipeline.orchestrator import _process_company
from app.repositories import companies as companies_repo

log = get_logger(__name__)


@celery.task(name="app.tasks.scrape.scrape_company", autoretry_for=(Exception,), max_retries=2)
def scrape_company(company_slug: str) -> dict:
    """Manual single-company scrape (used by the dashboard 'refresh' button)."""
    configure_logging()
    return asyncio.run(_scrape_company_async(company_slug))


async def _scrape_company_async(company_slug: str) -> dict:
    async with session_scope() as session:
        company = await companies_repo.get_by_slug(session, company_slug)
    if company is None:
        return {"status": "not_found", "slug": company_slug}
    result = await _process_company(company)
    return {
        "status": result.status,
        "slug": company_slug,
        "new": result.new,
        "updated": result.updated,
        "closed": result.closed,
        "error": result.error,
    }


@celery.task(name="app.tasks.scrape.scrape_source", autoretry_for=(Exception,), max_retries=2)
def scrape_source(source: str) -> dict:
    configure_logging()
    return asyncio.run(_scrape_source_async(source))


async def _scrape_source_async(source: str) -> dict:
    try:
        src_enum = Source(source)
    except ValueError:
        return {"status": "invalid_source", "source": source}
    async with session_scope() as session:
        companies = await companies_repo.list_active_by_source(session, src_enum)

    tallies = {"new": 0, "updated": 0, "closed": 0, "failed": 0}
    for company in companies:
        result = await _process_company(company)
        tallies["new"] += result.new
        tallies["updated"] += result.updated
        tallies["closed"] += result.closed
        if result.status == "failed":
            tallies["failed"] += 1
    return {"status": "ok", "source": source, **tallies}
