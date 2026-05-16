from __future__ import annotations

from pathlib import Path

from app.ai.client import complete
from app.config import settings
from app.db.models import Job
from app.db.session import session_scope
from app.repositories import ai_analyses as ai_repo
from app.repositories import jobs as jobs_repo
from app.utils.hashing import prompt_hash

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "cover_letter.txt").read_text(
    encoding="utf-8"
)
_SYSTEM = "You write concise, sincere cover letters as plain text. Never use markdown."


def _build_prompt(job: Job) -> str:
    return _PROMPT_TEMPLATE.format(
        resume_summary=settings.resume_summary,
        title=job.title,
        company=job.company.name if job.company else "(unknown)",
        location=job.location or "(unspecified)",
        description=(job.description_text or "")[:3500],
    )


async def generate_cover_letter(job_id: int) -> str:
    """Return cover letter text. Caches per (job, prompt_hash) so re-asks are free."""
    async with session_scope() as session:
        job = await jobs_repo.get_by_id(session, job_id)
        if job is None:
            raise ValueError(f"job {job_id} not found")
        _ = job.company
        prompt = _build_prompt(job)
        ph = prompt_hash(prompt)
        cached = await ai_repo.find_cached(session, job_id=job_id, kind="cover_letter", prompt_hash=ph)
        if cached:
            return cached.content

    text = await complete(system=_SYSTEM, user=prompt, max_tokens=600, temperature=0.6)
    async with session_scope() as session:
        await ai_repo.save(
            session,
            job_id=job_id,
            kind="cover_letter",
            prompt_hash=ph,
            model=settings.anthropic_model,
            content=text,
        )
    return text
