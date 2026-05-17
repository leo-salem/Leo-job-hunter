from __future__ import annotations

from fastapi import APIRouter

from app.tasks.daily import daily_scrape
from app.tasks.scrape import scrape_company, scrape_source

router = APIRouter(prefix="/api/trigger", tags=["trigger"])


@router.post("/daily")
async def trigger_daily():
    res = daily_scrape.apply_async()
    return {"task_id": res.id, "status": "queued"}


@router.post("/company/{slug}")
async def trigger_company(slug: str):
    res = scrape_company.apply_async(args=[slug])
    return {"task_id": res.id, "status": "queued", "slug": slug}


@router.post("/source/{source}")
async def trigger_source(source: str):
    res = scrape_source.apply_async(args=[source])
    return {"task_id": res.id, "status": "queued", "source": source}
