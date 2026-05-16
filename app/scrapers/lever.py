from __future__ import annotations

from typing import Iterable

from app.db.models import Company
from app.logging_setup import get_logger
from app.schemas.job import RawJob
from app.scrapers.base import BaseScraper, ScraperError, html_to_text
from app.utils.http import get_json, http_client
from app.utils.time import parse_epoch_ms

log = get_logger(__name__)


class LeverScraper(BaseScraper):
    source = "lever"

    BASE = "https://api.lever.co/v0/postings/{site}?mode=json"

    async def fetch(self, company: Company) -> Iterable[RawJob]:
        url = self.BASE.format(site=company.external_id)
        async with http_client() as client:
            try:
                payload = await get_json(client, url)
            except Exception as e:  # noqa: BLE001
                raise ScraperError(f"lever fetch failed for {company.slug}: {e}") from e

        if not isinstance(payload, list):
            raise ScraperError(f"lever: unexpected payload for {company.slug}")

        out: list[RawJob] = []
        for item in payload:
            try:
                out.append(self._to_raw(item))
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "lever_parse_skip",
                    company=company.slug,
                    job_id=item.get("id"),
                    error=str(e),
                )
        return out

    def _to_raw(self, item: dict) -> RawJob:
        external_id = str(item["id"])
        title = item.get("text") or ""
        apply_url = item.get("hostedUrl") or item.get("applyUrl") or ""
        cats = item.get("categories") or {}
        location = cats.get("location")
        country = location  # Lever exposes country/region inline; good enough for normalization
        commitment = cats.get("commitment")  # Full-time, Internship, etc.
        department = cats.get("department")
        team = cats.get("team")

        desc_html_parts: list[str] = []
        if item.get("descriptionHtml"):
            desc_html_parts.append(item["descriptionHtml"])
        for block in item.get("lists") or []:
            text = block.get("text") or ""
            content = block.get("content") or ""
            desc_html_parts.append(f"<h3>{text}</h3>{content}")
        if item.get("additionalHtml") or item.get("additional"):
            desc_html_parts.append(item.get("additionalHtml") or item.get("additional"))
        description_html = "\n".join(p for p in desc_html_parts if p) or None

        all_locations = cats.get("allLocations") or []
        remote_flag = any("remote" in (loc or "").lower() for loc in [location, *all_locations])
        workplace = (item.get("workplaceType") or "").lower()
        if workplace == "remote":
            remote_flag = True

        return RawJob(
            source="lever",
            external_id=external_id,
            title=title.strip(),
            apply_url=apply_url,
            location=location,
            country=country,
            remote=remote_flag,
            employment_type=commitment,
            department=department,
            team=team,
            description_html=description_html,
            description_text=html_to_text(description_html) or item.get("descriptionPlain"),
            posted_at=parse_epoch_ms(item.get("createdAt")),
            updated_at_source=parse_epoch_ms(item.get("updatedAt") or item.get("createdAt")),
            raw_payload=item,
        )
