"""Idempotently load app/companies.yaml into the database."""
from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from app.db.models import Region, Source
from app.db.session import session_scope
from app.logging_setup import configure_logging, get_logger
from app.repositories import companies as companies_repo

log = get_logger(__name__)


async def main() -> None:
    configure_logging()
    config_path = Path(__file__).resolve().parent.parent / "app" / "companies.yaml"
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    entries = raw.get("companies") or []
    async with session_scope() as session:
        for entry in entries:
            try:
                src = Source(entry["source"])
            except ValueError:
                log.warning("seed_skip_unknown_source", entry=entry)
                continue
            try:
                region = Region(entry.get("target_region", "INTERNATIONAL"))
            except ValueError:
                region = Region.INTERNATIONAL
            await companies_repo.upsert(
                session,
                slug=entry["slug"],
                name=entry["name"],
                source=src,
                external_id=entry["external_id"],
                careers_url=entry.get("careers_url"),
                config=entry.get("config") or {},
                target_region=region,
            )
    log.info("seed_complete", count=len(entries))


if __name__ == "__main__":
    asyncio.run(main())
