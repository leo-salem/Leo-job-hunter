from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.db.models import Company
from app.db.session import session_scope
from app.logging_setup import get_logger
from app.pipeline.dedupe import job_fingerprint
from app.pipeline.filters import passes_for_region
from app.pipeline.normalizer import apply_updates, new_job_from_raw
from app.repositories import companies as companies_repo
from app.repositories import jobs as jobs_repo
from app.repositories import scrape_logs as scrape_logs_repo
from app.scrapers.base import ScraperError
from app.scrapers.registry import get_scraper
from app.utils.time import now_utc

log = get_logger(__name__)


@dataclass
class CompanyResult:
    company_slug: str
    seen: int = 0
    new: int = 0
    updated: int = 0
    closed: int = 0
    status: str = "ok"
    error: str | None = None


@dataclass
class RunResult:
    companies: list[CompanyResult]

    @property
    def total_new(self) -> int:
        return sum(c.new for c in self.companies)

    @property
    def total_updated(self) -> int:
        return sum(c.updated for c in self.companies)

    @property
    def total_closed(self) -> int:
        return sum(c.closed for c in self.companies)

    @property
    def total_failed(self) -> int:
        return sum(1 for c in self.companies if c.status == "failed")


async def run_daily() -> RunResult:
    """Scrape every active company. Never raise — log each failure individually."""
    async with session_scope() as session:
        all_companies = await companies_repo.list_active(session)

    results: list[CompanyResult] = []
    for company in all_companies:
        try:
            results.append(await _process_company(company))
        except Exception as e:  # noqa: BLE001
            log.exception("company_run_unexpected_failure", company=company.slug)
            results.append(
                CompanyResult(
                    company_slug=company.slug,
                    status="failed",
                    error=f"{type(e).__name__}: {e}",
                )
            )

    # Only record success if at least one company completed cleanly
    if any(r.status == "ok" for r in results):
        async with session_scope() as session:
            await scrape_logs_repo.mark_daily_success(session)

    log.info(
        "daily_run_finished",
        total_companies=len(results),
        ok=sum(1 for r in results if r.status == "ok"),
        failed=sum(1 for r in results if r.status == "failed"),
        new=sum(r.new for r in results),
        updated=sum(r.updated for r in results),
        closed=sum(r.closed for r in results),
    )
    return RunResult(companies=results)


async def _process_company(company: Company) -> CompanyResult:
    result = CompanyResult(company_slug=company.slug)

    # Open a scrape log row
    async with session_scope() as session:
        scrape_log = await scrape_logs_repo.create(
            session, source=company.source, company_slug=company.slug
        )
        scrape_log_id = scrape_log.id

    scraper = get_scraper(company.source)
    try:
        raw_jobs = list(await scraper.fetch(company))
    except ScraperError as e:
        await _finalize_failure(scrape_log_id, e, "ScraperError")
        result.status = "failed"
        result.error = str(e)
        return result
    except Exception as e:  # noqa: BLE001
        log.exception("scraper_unexpected", company=company.slug)
        await _finalize_failure(scrape_log_id, e, type(e).__name__)
        result.status = "failed"
        result.error = f"{type(e).__name__}: {e}"
        return result

    seen_fingerprints: set[str] = set()
    accepted: list = []  # list of (raw, normalized_country)

    for raw in raw_jobs:
        result.seen += 1
        seen_fingerprints.add(job_fingerprint(raw))
        passes, country = passes_for_region(raw, company.target_region)
        if passes:
            accepted.append((raw, country))

    # Pull tombstones once per company-run so we skip anything the user permanently deleted
    async with session_scope() as session:
        tombstoned = await jobs_repo.tombstoned_fingerprints(session)

    accepted = [(raw, country) for raw, country in accepted if job_fingerprint(raw) not in tombstoned]

    # Single transaction for all upserts + closed detection — keeps the run atomic per company
    async with session_scope() as session:
        for raw, country in accepted:
            try:
                outcome = await _upsert_job(session, company.id, raw, country, company.target_region)
                if outcome == "new":
                    result.new += 1
                elif outcome == "updated":
                    result.updated += 1
            except Exception:  # noqa: BLE001
                log.exception(
                    "persist_failed", company=company.slug, ext_id=raw.external_id
                )

        # Anything previously ACTIVE for this company that we didn't see → CLOSED
        ids_to_close = await jobs_repo.ids_to_close_for_company(
            session, company.id, seen_fingerprints
        )
        result.closed = await jobs_repo.mark_closed(session, ids_to_close)

        # Finalize the log row within the same transaction
        sl = await session.get(__scrape_log_cls(), scrape_log_id)
        if sl is not None:
            await scrape_logs_repo.finish(
                session,
                sl,
                status="ok",
                jobs_seen=result.seen,
                jobs_new=result.new,
                jobs_updated=result.updated,
                jobs_closed=result.closed,
            )

    return result


async def _upsert_job(session, company_id: int, raw, country: str | None, region) -> str:
    """Returns 'new' | 'updated' | 'noop'."""
    fp = job_fingerprint(raw)
    existing = await jobs_repo.get_by_fingerprint(session, fp)
    if existing is None:
        session.add(new_job_from_raw(raw, company_id=company_id, normalized_country=country, region=region))
        try:
            await session.flush()
            return "new"
        except IntegrityError:
            await session.rollback()
            # Another worker beat us — fall through to update path
            existing = await jobs_repo.get_by_fingerprint(session, fp)
            if existing is None:
                return "noop"
    changed = apply_updates(existing, raw, normalized_country=country)
    existing.last_seen_at = now_utc()
    return "updated" if changed else "noop"


async def _finalize_failure(scrape_log_id: int, exc: Exception, kind: str) -> None:
    async with session_scope() as session:
        sl = await session.get(__scrape_log_cls(), scrape_log_id)
        if sl is not None:
            await scrape_logs_repo.finish(
                session,
                sl,
                status="failed",
                error_message=str(exc),
                error_kind=kind,
            )


def __scrape_log_cls():
    from app.db.models import ScrapeLog

    return ScrapeLog
