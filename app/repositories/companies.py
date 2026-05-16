from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company, Region, Source


async def list_active(session: AsyncSession) -> list[Company]:
    stmt = select(Company).where(Company.active.is_(True)).order_by(Company.slug)
    return list((await session.execute(stmt)).scalars())


async def list_active_by_source(session: AsyncSession, source: Source) -> list[Company]:
    stmt = (
        select(Company)
        .where(Company.active.is_(True), Company.source == source)
        .order_by(Company.slug)
    )
    return list((await session.execute(stmt)).scalars())


async def get_by_slug(session: AsyncSession, slug: str) -> Company | None:
    stmt = select(Company).where(Company.slug == slug)
    return (await session.execute(stmt)).scalar_one_or_none()


async def upsert(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    source: Source,
    external_id: str,
    careers_url: str | None = None,
    config: dict | None = None,
    target_region: Region = Region.INTERNATIONAL,
) -> Company:
    existing = await get_by_slug(session, slug)
    if existing:
        existing.name = name
        existing.source = source
        existing.external_id = external_id
        existing.careers_url = careers_url
        existing.config = config or {}
        existing.active = True
        existing.target_region = target_region
        return existing
    new = Company(
        slug=slug,
        name=name,
        source=source,
        external_id=external_id,
        careers_url=careers_url,
        config=config or {},
        active=True,
        target_region=target_region,
    )
    session.add(new)
    return new
