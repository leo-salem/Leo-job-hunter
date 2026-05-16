from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.tasks.daily import daily_scrape_and_analyze
from app.tasks.scrape import scrape_company, scrape_source
from app.tasks.analyze import analyze_one

router = APIRouter(prefix="/api/trigger", tags=["trigger"])


@router.post("/daily")
async def trigger_daily():
    res = daily_scrape_and_analyze.apply_async()
    return {"task_id": res.id, "status": "queued"}


@router.post("/company/{slug}")
async def trigger_company(slug: str):
    res = scrape_company.apply_async(args=[slug])
    return {"task_id": res.id, "status": "queued", "slug": slug}


@router.post("/source/{source}")
async def trigger_source(source: str):
    res = scrape_source.apply_async(args=[source])
    return {"task_id": res.id, "status": "queued", "source": source}


@router.post("/analyze/{job_id}")
async def trigger_analyze(job_id: int):
    res = analyze_one.apply_async(args=[job_id])
    return {"task_id": res.id, "status": "queued", "job_id": job_id}


@router.post("/ai/cover-letter/{job_id}")
async def trigger_cover_letter(job_id: int):
    from app.ai.cover_letter import generate_cover_letter

    try:
        text = await generate_cover_letter(job_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, str(e)) from e
    return {"job_id": job_id, "cover_letter": text}


@router.post("/ai/tailored-summary/{job_id}")
async def trigger_tailored(job_id: int):
    from app.ai.resume_tailor import generate_tailored_summary

    try:
        text = await generate_tailored_summary(job_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, str(e)) from e
    return {"job_id": job_id, "summary": text}
