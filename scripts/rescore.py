"""Recompute heuristic_score + breakdown for every job in the database.

Useful after:
  - First migration to a schema with heuristic_score
  - Tweaking weights in app/pipeline/scoring_rules.py
  - Adding companies to app/pipeline/scoring_company.py

Idempotent. Safe to run any number of times.

    docker compose exec api python -m scripts.rescore
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Job
from app.db.session import session_scope
from app.logging_setup import configure_logging, get_logger
from app.pipeline.scoring import score_job

log = get_logger(__name__)


async def main() -> None:
    configure_logging()
    updated = 0
    unchanged = 0
    async with session_scope() as session:
        stmt = select(Job).options(selectinload(Job.company))
        jobs = list((await session.execute(stmt)).scalars())
        for j in jobs:
            result = score_job(
                title=j.title,
                description_text=j.description_text,
                remote=j.remote,
                country=j.country,
                region=j.region,
                posted_at=j.posted_at,
                company_name=j.company.name if j.company else None,
                source=j.source.value if hasattr(j.source, "value") else str(j.source),
            )
            new_score = float(result.score)
            new_confidence = float(result.confidence)
            new_breakdown = result.to_dict()
            if (
                j.heuristic_score != new_score
                or j.heuristic_confidence != new_confidence
                or j.score_breakdown != new_breakdown
            ):
                j.heuristic_score = new_score
                j.heuristic_confidence = new_confidence
                j.score_breakdown = new_breakdown
                updated += 1
            else:
                unchanged += 1
    log.info("rescore_complete", scanned=len(jobs), updated=updated, unchanged=unchanged)


if __name__ == "__main__":
    asyncio.run(main())
