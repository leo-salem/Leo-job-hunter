from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AIAnalysis


async def find_cached(
    session: AsyncSession, *, job_id: int, kind: str, prompt_hash: str
) -> AIAnalysis | None:
    stmt = select(AIAnalysis).where(
        AIAnalysis.job_id == job_id,
        AIAnalysis.kind == kind,
        AIAnalysis.prompt_hash == prompt_hash,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def save(
    session: AsyncSession,
    *,
    job_id: int,
    kind: str,
    prompt_hash: str,
    model: str,
    content: str,
    score: float | None = None,
    extra: dict | None = None,
) -> AIAnalysis:
    obj = AIAnalysis(
        job_id=job_id,
        kind=kind,
        prompt_hash=prompt_hash,
        model=model,
        content=content,
        score=score,
        extra=extra or {},
    )
    session.add(obj)
    await session.flush()
    return obj
