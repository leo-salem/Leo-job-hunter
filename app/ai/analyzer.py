from __future__ import annotations

import json
import re
from pathlib import Path

from app.ai.client import complete
from app.config import settings
from app.db.models import Job
from app.db.session import session_scope
from app.logging_setup import get_logger
from app.repositories import ai_analyses as ai_repo
from app.repositories import jobs as jobs_repo
from app.utils.hashing import prompt_hash

log = get_logger(__name__)

_PROMPT_FILE = Path(__file__).parent / "prompts" / "analyze_job.txt"
_PROMPT_TEMPLATE = _PROMPT_FILE.read_text(encoding="utf-8")

_SYSTEM = (
    "You are a precise hiring-fit evaluator. You always reply with exactly one JSON "
    "object on a single line and never with prose or markdown fences."
)

_MAX_DESC_CHARS = 3500


def _build_prompt(job: Job) -> str:
    desc = (job.description_text or "")[:_MAX_DESC_CHARS]
    return _PROMPT_TEMPLATE.format(
        resume_summary=settings.resume_summary,
        title=job.title,
        company=job.company.name if job.company else "(unknown)",
        location=job.location or "(unspecified)",
        remote="yes" if job.remote else "no",
        employment_type=job.employment_type or "(unspecified)",
        description=desc or "(no description provided)",
    )


def _parse_response(text: str) -> dict | None:
    """Pull the first {...} JSON object out of the response."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


async def score_job(job_id: int) -> dict:
    """Score a single job, cache result, persist score + summary on the Job row."""
    async with session_scope() as session:
        job = await jobs_repo.get_by_id(session, job_id)
        if job is None:
            return {"status": "missing", "job_id": job_id}
        # Load company eagerly via accessor
        _ = job.company  # noqa: F841 — touches the relationship for use in prompt builder
        prompt_text = _build_prompt(job)
        ph = prompt_hash(prompt_text)

        cached = await ai_repo.find_cached(session, job_id=job_id, kind="score", prompt_hash=ph)
        if cached is not None:
            job.ai_score = cached.score
            try:
                extra = cached.extra or {}
                job.ai_summary = extra.get("summary") or cached.content
            except Exception:  # noqa: BLE001
                job.ai_summary = cached.content
            return {"status": "cached", "job_id": job_id, "score": cached.score}

    # Call API outside the DB transaction so we don't hold a connection during network I/O
    try:
        raw = await complete(system=_SYSTEM, user=prompt_text, max_tokens=400, temperature=0.2)
    except Exception as e:  # noqa: BLE001
        log.exception("ai_call_failed", job_id=job_id)
        return {"status": "error", "job_id": job_id, "error": str(e)}

    parsed = _parse_response(raw)
    if not parsed or "score" not in parsed:
        log.warning("ai_unparseable", job_id=job_id, raw=raw[:200])
        return {"status": "unparseable", "job_id": job_id}

    try:
        score = float(parsed.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    summary = str(parsed.get("summary") or "")[:500]

    async with session_scope() as session:
        await ai_repo.save(
            session,
            job_id=job_id,
            kind="score",
            prompt_hash=ph,
            model=settings.anthropic_model,
            content=raw,
            score=score,
            extra={
                "summary": summary,
                "red_flags": parsed.get("red_flags") or [],
                "highlights": parsed.get("highlights") or [],
            },
        )
        job = await jobs_repo.get_by_id(session, job_id)
        if job is not None:
            job.ai_score = score
            job.ai_summary = summary

    return {"status": "ok", "job_id": job_id, "score": score}
