from __future__ import annotations

from typing import Iterable

from app.db.models import Company
from app.logging_setup import get_logger
from app.schemas.job import RawJob
from app.scrapers.base import BaseScraper, ScraperError, html_to_text
from app.utils.http import get_json, http_client
from app.utils.time import parse_dt

log = get_logger(__name__)


class GreenhouseScraper(BaseScraper):
    source = "greenhouse"

    BASE = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"

    async def fetch(self, company: Company, *, skip_fingerprints: set[str] | None = None) -> Iterable[RawJob]:
        url = self.BASE.format(token=company.external_id)
        async with http_client() as client:
            try:
                payload = await get_json(client, url)
            except Exception as e:  # noqa: BLE001
                raise ScraperError(f"greenhouse fetch failed for {company.slug}: {e}") from e

        if not isinstance(payload, dict):
            raise ScraperError(f"greenhouse: unexpected payload for {company.slug}")

        jobs_data = payload.get("jobs") or []
        out: list[RawJob] = []
        for item in jobs_data:
            try:
                out.append(self._to_raw(item))
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "greenhouse_parse_skip",
                    company=company.slug,
                    job_id=item.get("id"),
                    error=str(e),
                )
        return out

    def _to_raw(self, item: dict) -> RawJob:
        external_id = str(item["id"])
        title = item.get("title") or ""
        apply_url = item.get("absolute_url") or ""
        location_obj = item.get("location") or {}
        location = location_obj.get("name") if isinstance(location_obj, dict) else None
        content = item.get("content") or ""  # HTML-escaped string per Greenhouse docs
        # Greenhouse returns HTML-escaped content; un-escape if needed
        if content and "&lt;" in content:
            import html as _html

            content = _html.unescape(content)
        offices = item.get("offices") or []
        departments = item.get("departments") or []
        department = departments[0]["name"] if departments and isinstance(departments[0], dict) else None
        team = None
        country = None
        if offices and isinstance(offices[0], dict):
            country = offices[0].get("location") or offices[0].get("name")

        return RawJob(
            source="greenhouse",
            external_id=external_id,
            title=title.strip(),
            apply_url=apply_url,
            location=location,
            country=country,
            remote=_looks_remote(location),
            department=department,
            team=team,
            description_html=content or None,
            description_text=html_to_text(content),
            posted_at=parse_dt(item.get("first_published") or item.get("updated_at")),
            updated_at_source=parse_dt(item.get("updated_at")),
            raw_payload=item,
        )


def _looks_remote(loc: str | None) -> bool:
    if not loc:
        return False
    s = loc.lower()
    return "remote" in s or "anywhere" in s or "distributed" in s
