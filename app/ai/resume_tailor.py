from __future__ import annotations

from pathlib import Path

from app.ai.client import complete
from app.config import settings
from app.db.models import Job
from app.db.session import session_scope
from app.repositories import ai_analyses as ai_repo
from app.repositories import jobs as jobs_repo
from app.utils.hashing import prompt_hash

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "resume_summary.txt").read_text(
    encoding="utf-8"
)
_SYSTEM = "You rewrite resume summaries truthfully and concisely. No markdown."


def _build_prompt(job: Job) -> str:
    return _PROMPT_TEMPLATE.format(
        resume_summary=settings.resume_summary,
        title=job.title,
        company=job.company.name if job.company else "(unknown)",
        description=(job.description_text or "")[:3500],
    )


async def generate_tailored_summary(job_id: int) -> str:
    async with session_scope() as session:
        job = await jobs_repo.get_by_id(session, job_id)
        if job is None:
            raise ValueError(f"job {job_id} not found")
        _ = job.company
        prompt = _build_prompt(job)
        ph = prompt_hash(prompt)
        cached = await ai_repo.find_cached(session, job_id=job_id, kind="resume_summary", prompt_hash=ph)
        if cached:
            return cached.content

    text = await complete(system=_SYSTEM, user=prompt, max_tokens=200, temperature=0.4)
    async with session_scope() as session:
        await ai_repo.save(
            session,
            job_id=job_id,
            kind="resume_summary",
            prompt_hash=ph,
            model=settings.anthropic_model,
            content=text,
        )
    return text
