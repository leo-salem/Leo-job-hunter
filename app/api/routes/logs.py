from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.repositories import scrape_logs as scrape_logs_repo

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
async def list_logs(limit: int = 100, session: AsyncSession = SessionDep):
    logs = await scrape_logs_repo.recent(session, limit=limit)
    return [
        {
            "id": l.id,
            "started_at": l.started_at.isoformat() if l.started_at else None,
            "finished_at": l.finished_at.isoformat() if l.finished_at else None,
            "source": l.source.value if l.source else None,
            "company_slug": l.company_slug,
            "status": l.status,
            "jobs_seen": l.jobs_seen,
            "jobs_new": l.jobs_new,
            "jobs_updated": l.jobs_updated,
            "jobs_closed": l.jobs_closed,
            "error_message": l.error_message,
            "error_kind": l.error_kind,
        }
        for l in logs
    ]
