from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.api.routes import companies as companies_routes
from app.api.routes import jobs as jobs_routes
from app.api.routes import logs as logs_routes
from app.api.routes import trigger as trigger_routes
from app.db.models import ApplicationStatus, JobLifecycle, Region, Source
from app.logging_setup import configure_logging, get_logger
from app.repositories import jobs as jobs_repo
from app.repositories import scrape_logs as scrape_logs_repo

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("startup")
    # No auto-refresh on startup. Scrapes are user-initiated only:
    #   - start.bat (runs scripts.run_once)
    #   - "Refresh now" button (POST /refresh)
    yield
    log.info("shutdown")


app = FastAPI(title="Job Hunter", lifespan=lifespan)

# --- Static + templates ---
TEMPLATES_DIR = Path(__file__).parent / "dashboard" / "templates"
STATIC_DIR = Path(__file__).parent / "dashboard" / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# --- API routers (JSON) ---
app.include_router(jobs_routes.router)
app.include_router(companies_routes.router)
app.include_router(logs_routes.router)
app.include_router(trigger_routes.router)


# --- Dashboard (HTML) ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, session: AsyncSession = SessionDep):
    int_jobs = await jobs_repo.search_jobs(
        session,
        region=Region.INTERNATIONAL,
        lifecycles=[JobLifecycle.ACTIVE],
        statuses=[ApplicationStatus.NOT_APPLIED],
        limit=10000,
        order_by="newest",
    )
    eg_jobs = await jobs_repo.search_jobs(
        session,
        region=Region.EGYPT,
        lifecycles=[JobLifecycle.ACTIVE],
        statuses=[ApplicationStatus.NOT_APPLIED],
        limit=10000,
        order_by="newest",
    )
    last_run = await scrape_logs_repo.get_last_successful_daily(session)
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "international_count": len(int_jobs),
            "egypt_count": len(eg_jobs),
            "last_run": last_run.strftime("%Y-%m-%d %H:%M") if last_run else None,
        },
    )


@app.get("/international", response_class=HTMLResponse)
async def dashboard_international(
    request: Request,
    q: str | None = None,
    source: str | None = None,
    country: str | None = None,
    status: str = "NOT_APPLIED",
    lifecycle: str = "ACTIVE",
    min_score: str | None = None,
    remote: bool = False,
    favorites: bool = False,
    session: AsyncSession = SessionDep,
):
    return await _render_region_dashboard(
        request, session, Region.INTERNATIONAL,
        q=q, source=source, country=country, status=status, lifecycle=lifecycle,
        min_score=min_score, remote=remote, favorites=favorites,
    )


@app.get("/egypt", response_class=HTMLResponse)
async def dashboard_egypt(
    request: Request,
    q: str | None = None,
    source: str | None = None,
    country: str | None = None,
    status: str = "NOT_APPLIED",
    lifecycle: str = "ACTIVE",
    min_score: str | None = None,
    remote: bool = False,
    favorites: bool = False,
    session: AsyncSession = SessionDep,
):
    return await _render_region_dashboard(
        request, session, Region.EGYPT,
        q=q, source=source, country=country, status=status, lifecycle=lifecycle,
        min_score=min_score, remote=remote, favorites=favorites,
    )


async def _render_region_dashboard(
    request: Request,
    session: AsyncSession,
    region: Region,
    *,
    q: str | None,
    source: str | None,
    country: str | None,
    status: str,
    lifecycle: str,
    min_score: str | None,
    remote: bool,
    favorites: bool,
):
    lifecycles = _parse_enum_list(lifecycle, JobLifecycle)
    statuses = _parse_enum_list(status, ApplicationStatus) if status else None
    sources = [Source(source)] if source else None
    countries = [country] if country else None
    min_score_val = float(min_score) if min_score else None

    jobs = await jobs_repo.search_jobs(
        session,
        region=region,
        lifecycles=lifecycles,
        statuses=statuses,
        sources=sources,
        countries=countries,
        remote_only=remote,
        favorites_only=favorites,
        min_score=min_score_val,
        query=q,
        limit=500,
        order_by="score",
    )
    for j in jobs:
        _ = j.company

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "region": region.value,
            "jobs": jobs,
            "total": len(jobs),
            "all_sources": [s.value for s in Source],
            "filters": {
                "q": q,
                "source": source,
                "country": country,
                "status": status,
                "lifecycle": lifecycle,
                "min_score": min_score or "",
                "remote": remote,
                "favorites": favorites,
            },
        },
    )


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def dashboard_job(
    request: Request, job_id: int, session: AsyncSession = SessionDep
):
    job = await jobs_repo.get_by_id(session, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    _ = job.company
    return templates.TemplateResponse(
        "job_detail.html",
        {
            "request": request,
            "job": job,
            "region": job.region.value,
        },
    )


@app.get("/jobs/{job_id}/score-debug", response_class=HTMLResponse)
async def score_debug(
    request: Request, job_id: int, session: AsyncSession = SessionDep
):
    """Why did this job score what it scored?

    Recomputes features live (in case the engine changed since the row was
    scored) but uses the stored breakdown when available."""
    from app.pipeline.scoring_features import build_features
    from app.pipeline.scoring_strategy import strategy_for

    job = await jobs_repo.get_by_id(session, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    _ = job.company

    features = build_features(
        title=job.title,
        description_text=job.description_text,
        remote=job.remote,
        country=job.country,
        region=job.region,
        posted_at=job.posted_at,
        company_name=job.company.name if job.company else None,
        source=job.source.value,
    )
    strategy = strategy_for(job.region)
    features_view = {
        "title_norm": features.title_norm,
        "seniority": features.seniority.value,
        "specialization": features.specialization.value,
        "exp_required": features.experience.required_years,
        "exp_grad_friendly": features.experience.has_grad_friendly_phrase,
        "stack_title": sorted(features.stack_in_title_keys),
        "stack_desc": sorted(features.stack_keys - features.stack_in_title_keys),
        "description_chars": features.description_chars,
    }

    return templates.TemplateResponse(
        "score_debug.html",
        {
            "request": request,
            "job": job,
            "region": job.region.value,
            "b": job.score_breakdown,
            "features": features_view,
            "strategy_description": strategy.description,
        },
    )


@app.get("/logs", response_class=HTMLResponse)
async def dashboard_logs(request: Request, session: AsyncSession = SessionDep):
    logs = await scrape_logs_repo.recent(session, limit=200)
    return templates.TemplateResponse(
        "logs.html", {"request": request, "logs": logs}
    )


# --- HTMX action endpoints (return either an empty body to delete the row,
#     or a re-rendered partial to update it in place) ---

async def _row_response(request: Request, job, *, removed: bool):
    if removed:
        return Response(status_code=200, content="")
    return templates.TemplateResponse(
        "partials/job_row.html", {"request": request, "j": job}
    )


@app.post("/jobs/{job_id}/apply")
async def htmx_apply(
    request: Request, job_id: int, session: AsyncSession = SessionDep
):
    job = await jobs_repo.set_application_status(session, job_id, ApplicationStatus.APPLIED)
    if job is None:
        raise HTTPException(404)
    if _is_htmx(request):
        return await _row_response(request, job, removed=True)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/unapply")
async def htmx_unapply(
    request: Request, job_id: int, session: AsyncSession = SessionDep
):
    job = await jobs_repo.set_application_status(session, job_id, ApplicationStatus.NOT_APPLIED)
    if job is None:
        raise HTTPException(404)
    if _is_htmx(request):
        _ = job.company
        return await _row_response(request, job, removed=False)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/reject")
async def htmx_reject(
    request: Request, job_id: int, session: AsyncSession = SessionDep
):
    job = await jobs_repo.set_application_status(session, job_id, ApplicationStatus.REJECTED)
    if job is None:
        raise HTTPException(404)
    if _is_htmx(request):
        return await _row_response(request, job, removed=True)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/favorite")
async def htmx_favorite(
    request: Request, job_id: int, session: AsyncSession = SessionDep
):
    job = await jobs_repo.toggle_favorite(session, job_id)
    if job is None:
        raise HTTPException(404)
    if _is_htmx(request):
        _ = job.company
        return await _row_response(request, job, removed=False)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/archive")
async def htmx_archive(
    request: Request, job_id: int, session: AsyncSession = SessionDep
):
    job = await jobs_repo.archive(session, job_id)
    if job is None:
        raise HTTPException(404)
    if _is_htmx(request):
        return await _row_response(request, job, removed=True)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/submitted")
async def htmx_submitted(
    request: Request, job_id: int, session: AsyncSession = SessionDep
):
    """Hard-delete the job. No recovery — vanishes forever."""
    ok = await jobs_repo.delete_job(session, job_id)
    if not ok:
        raise HTTPException(404)
    if _is_htmx(request):
        return Response(status_code=200, content="")
    return RedirectResponse(url="/", status_code=303)


@app.post("/jobs/{job_id}/notes")
async def save_notes(
    job_id: int, text: str = Form(""), session: AsyncSession = SessionDep
):
    await jobs_repo.set_notes(session, job_id, text or None)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/refresh", response_class=HTMLResponse)
async def refresh_synchronous():
    """Run the full scrape pipeline inline. Blocks until done (~2 min)."""
    from app.pipeline.orchestrator import run_daily

    result = await run_daily()
    return HTMLResponse(
        f'<span class="muted small">Refresh complete: '
        f'+{result.total_new} new, {result.total_updated} updated, '
        f'{result.total_closed} closed, {result.total_failed} failed.</span>'
    )


# --- Helpers ---

def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _parse_enum_list(value: str, enum_cls):
    if not value:
        return None
    out = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(enum_cls(part))
        except ValueError:
            continue
    return out or None


