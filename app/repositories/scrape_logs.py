from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ScrapeLog, Source, SystemState, KEY_LAST_SUCCESSFUL_DAILY
from app.utils.time import now_utc


async def create(
    session: AsyncSession,
    *,
    source: Source | None,
    company_slug: str | None,
) -> ScrapeLog:
    log = ScrapeLog(source=source, company_slug=company_slug, status="running")
    session.add(log)
    await session.flush()
    return log


async def finish(
    session: AsyncSession,
    log: ScrapeLog,
    *,
    status: str,
    jobs_seen: int = 0,
    jobs_new: int = 0,
    jobs_updated: int = 0,
    jobs_closed: int = 0,
    error_message: str | None = None,
    error_kind: str | None = None,
) -> None:
    log.finished_at = now_utc()
    log.status = status
    log.jobs_seen = jobs_seen
    log.jobs_new = jobs_new
    log.jobs_updated = jobs_updated
    log.jobs_closed = jobs_closed
    log.error_message = error_message
    log.error_kind = error_kind


async def recent(session: AsyncSession, limit: int = 100) -> list[ScrapeLog]:
    stmt = select(ScrapeLog).order_by(desc(ScrapeLog.started_at)).limit(limit)
    return list((await session.execute(stmt)).scalars())


async def get_state(session: AsyncSession, key: str) -> str | None:
    row = await session.get(SystemState, key)
    return row.value if row else None


async def set_state(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(SystemState, key)
    if row:
        row.value = value
    else:
        session.add(SystemState(key=key, value=value))


async def get_last_successful_daily(session: AsyncSession) -> datetime | None:
    raw = await get_state(session, KEY_LAST_SUCCESSFUL_DAILY)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


async def mark_daily_success(session: AsyncSession) -> None:
    await set_state(session, KEY_LAST_SUCCESSFUL_DAILY, now_utc().isoformat())
