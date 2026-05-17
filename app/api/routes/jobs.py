from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.db.models import ApplicationStatus, JobLifecycle, Source
from app.repositories import jobs as jobs_repo

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(
    lifecycle: str = "ACTIVE",
    status: str = "NOT_APPLIED",
    source: str | None = None,
    country: str | None = None,
    remote: bool = False,
    favorites: bool = False,
    min_score: float | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
    order: str = "score",
    session: AsyncSession = SessionDep,
):
    lifecycles = (
        [JobLifecycle(lc.strip()) for lc in lifecycle.split(",") if lc.strip()]
        if lifecycle
        else None
    )
    statuses = (
        [ApplicationStatus(s.strip()) for s in status.split(",") if s.strip()]
        if status
        else None
    )
    sources = (
        [Source(s.strip()) for s in source.split(",") if s.strip()] if source else None
    )
    countries = (
        [c.strip() for c in country.split(",") if c.strip()] if country else None
    )

    rows = await jobs_repo.search_jobs(
        session,
        lifecycles=lifecycles,
        statuses=statuses,
        sources=sources,
        countries=countries,
        remote_only=remote,
        favorites_only=favorites,
        min_score=min_score,
        query=q,
        limit=limit,
        offset=offset,
        order_by=order,
    )

    return [
        {
            "id": j.id,
            "title": j.title,
            "company": j.company.name if j.company else None,
            "location": j.location,
            "country": j.country,
            "remote": j.remote,
            "source": j.source.value,
            "apply_url": j.apply_url,
            "posted_at": j.posted_at.isoformat() if j.posted_at else None,
            "score": j.heuristic_score,
            "confidence": j.heuristic_confidence,
            "quality_label": (j.score_breakdown or {}).get("quality_label"),
            "lifecycle": j.lifecycle.value,
            "application_status": j.application_status.value,
            "favorite": j.favorite,
        }
        for j in rows
    ]


@router.post("/{job_id}/status")
async def set_status(
    job_id: int,
    status: str = Body(..., embed=True),
    session: AsyncSession = SessionDep,
):
    try:
        s = ApplicationStatus(status)
    except ValueError as e:
        raise HTTPException(400, f"invalid status: {status}") from e
    job = await jobs_repo.set_application_status(session, job_id, s)
    if job is None:
        raise HTTPException(404, "job not found")
    return {"id": job.id, "application_status": job.application_status.value}


@router.post("/{job_id}/favorite")
async def fav(job_id: int, session: AsyncSession = SessionDep):
    job = await jobs_repo.toggle_favorite(session, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return {"id": job.id, "favorite": job.favorite}


@router.post("/{job_id}/archive")
async def archive(job_id: int, session: AsyncSession = SessionDep):
    job = await jobs_repo.archive(session, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return {"id": job.id, "lifecycle": job.lifecycle.value}


@router.post("/{job_id}/notes")
async def notes(
    job_id: int,
    text: str = Body("", embed=True),
    session: AsyncSession = SessionDep,
):
    job = await jobs_repo.set_notes(session, job_id, text or None)
    if job is None:
        raise HTTPException(404, "job not found")
    return {"id": job.id, "notes": job.notes}


@router.get("/{job_id}")
async def get_job(job_id: int, session: AsyncSession = SessionDep):
    job = await jobs_repo.get_by_id(session, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company.name if job.company else None,
        "location": job.location,
        "country": job.country,
        "remote": job.remote,
        "employment_type": job.employment_type,
        "department": job.department,
        "source": job.source.value,
        "apply_url": job.apply_url,
        "posted_at": job.posted_at.isoformat() if job.posted_at else None,
        "first_seen_at": job.first_seen_at.isoformat() if job.first_seen_at else None,
        "score": job.heuristic_score,
        "confidence": job.heuristic_confidence,
        "quality_label": (job.score_breakdown or {}).get("quality_label"),
        "score_breakdown": job.score_breakdown,
        "lifecycle": job.lifecycle.value,
        "application_status": job.application_status.value,
        "favorite": job.favorite,
        "notes": job.notes,
        "description_text": job.description_text,
    }
