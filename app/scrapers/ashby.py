from __future__ import annotations

from typing import Iterable

from app.db.models import Company
from app.logging_setup import get_logger
from app.schemas.job import RawJob
from app.scrapers.base import BaseScraper, ScraperError, html_to_text
from app.utils.http import get_json, http_client
from app.utils.time import parse_dt

log = get_logger(__name__)


class AshbyScraper(BaseScraper):
    source = "ashby"

    BASE = "https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true"

    async def fetch(self, company: Company) -> Iterable[RawJob]:
        url = self.BASE.format(org=company.external_id)
        async with http_client() as client:
            try:
                payload = await get_json(client, url)
            except Exception as e:  # noqa: BLE001
                raise ScraperError(f"ashby fetch failed for {company.slug}: {e}") from e

        if not isinstance(payload, dict):
            raise ScraperError(f"ashby: unexpected payload for {company.slug}")

        jobs_data = payload.get("jobs") or []
        out: list[RawJob] = []
        for item in jobs_data:
            try:
                out.append(self._to_raw(item))
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "ashby_parse_skip",
                    company=company.slug,
                    job_id=item.get("id"),
                    error=str(e),
                )
        return out

    def _to_raw(self, item: dict) -> RawJob:
        external_id = str(item.get("id") or item.get("jobId") or item.get("externalId") or "")
        if not external_id:
            raise ValueError("ashby job missing id")

        title = item.get("title") or ""
        apply_url = item.get("applyUrl") or item.get("jobUrl") or ""
        location = item.get("location") or item.get("locationName")
        secondary_locations = item.get("secondaryLocations") or []
        secondary_names = [
            (loc.get("location") if isinstance(loc, dict) else loc)
            for loc in secondary_locations
        ]
        remote_flag = bool(item.get("isRemote")) or any(
            "remote" in (loc or "").lower() for loc in [location, *secondary_names]
        )
        country = None
        if isinstance(item.get("address"), dict):
            country = item["address"].get("postalAddress", {}).get("addressCountry")
        country = country or location

        description_html = item.get("descriptionHtml") or item.get("description")
        description_text = item.get("descriptionPlain") or html_to_text(description_html)

        return RawJob(
            source="ashby",
            external_id=external_id,
            title=title.strip(),
            apply_url=apply_url,
            location=location,
            country=country,
            remote=remote_flag,
            employment_type=item.get("employmentType"),
            department=item.get("department"),
            team=item.get("team"),
            description_html=description_html,
            description_text=description_text,
            posted_at=parse_dt(item.get("publishedAt") or item.get("publishedDate")),
            updated_at_source=parse_dt(item.get("updatedAt") or item.get("publishedAt")),
            raw_payload=item,
        )
