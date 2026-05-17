from __future__ import annotations

import asyncio
from typing import Iterable

from app.db.models import Company
from app.logging_setup import get_logger
from app.schemas.job import RawJob
from app.scrapers.base import BaseScraper, ScraperError, html_to_text
from app.utils.http import http_client, post_json
from app.utils.time import parse_dt

log = get_logger(__name__)


class WorkdayScraper(BaseScraper):
    """Generic Workday scraper.

    Each Workday tenant exposes the same JSON endpoint shape under a host-specific URL.
    Required config in Company.config:
      host:   e.g. "nvidia.wd5.myworkdayjobs.com"
      tenant: e.g. "nvidia"
      site:   e.g. "NVIDIAExternalCareerSite"
    Optional:
      facets: dict of pre-applied facet filters
      page_size: default 20
      max_pages: hard cap to avoid runaway pagination (default 25 → 500 jobs)
    """

    source = "workday"

    async def fetch(self, company: Company, *, skip_fingerprints: set[str] | None = None) -> Iterable[RawJob]:
        config = company.config or {}
        host = config.get("host")
        tenant = config.get("tenant")
        site = config.get("site")
        if not (host and tenant and site):
            raise ScraperError(
                f"workday: company {company.slug} missing host/tenant/site config"
            )

        page_size = int(config.get("page_size", 20))
        max_pages = int(config.get("max_pages", 25))
        applied_facets = config.get("facets") or {}

        list_url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
        detail_base = f"https://{host}/wday/cxs/{tenant}/{site}"

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": f"https://{host}",
            "Referer": f"https://{host}/en-US/{site}",
        }

        async with http_client(headers=headers) as client:
            out: list[RawJob] = []
            offset = 0
            for page_idx in range(max_pages):
                body = {
                    "appliedFacets": applied_facets,
                    "limit": page_size,
                    "offset": offset,
                    "searchText": "",
                }
                try:
                    payload = await post_json(client, list_url, json=body)
                except Exception as e:  # noqa: BLE001
                    raise ScraperError(
                        f"workday list fetch failed for {company.slug}: {e}"
                    ) from e

                if not isinstance(payload, dict):
                    raise ScraperError(
                        f"workday: unexpected payload for {company.slug}"
                    )
                postings = payload.get("jobPostings") or []
                if not postings:
                    break

                # Hydrate details concurrently but politely
                sem = asyncio.Semaphore(4)

                async def hydrate(item: dict) -> RawJob | None:
                    async with sem:
                        return await self._build_with_detail(client, detail_base, item)

                detailed = await asyncio.gather(
                    *(hydrate(item) for item in postings), return_exceptions=True
                )
                for d in detailed:
                    if isinstance(d, RawJob):
                        out.append(d)
                    elif isinstance(d, Exception):
                        log.warning(
                            "workday_detail_skip",
                            company=company.slug,
                            error=str(d),
                        )

                total = int(payload.get("total") or 0)
                offset += page_size
                if offset >= total:
                    break
                await asyncio.sleep(0.5)  # gentle pacing
            return out

    async def _build_with_detail(
        self, client, detail_base: str, item: dict
    ) -> RawJob | None:
        title = item.get("title") or ""
        external_path = item.get("externalPath") or ""
        external_id = external_path.rsplit("/", 1)[-1] if external_path else item.get("bulletFields", [""])[0]
        if not external_id:
            return None
        location = item.get("locationsText") or ""
        posted = item.get("postedOn")
        apply_url = f"https://{detail_base.split('/wday/cxs/')[0].replace('https://', '')}/en-US/{detail_base.rstrip('/').split('/')[-1]}{external_path}"
        apply_url = f"https://{detail_base.split('/wday/cxs/')[0].replace('https://', '')}{external_path}"
        # Reconstruct apply_url more cleanly:
        host = detail_base.split("/wday/cxs/")[0].replace("https://", "")
        site = detail_base.rstrip("/").split("/")[-1]
        apply_url = f"https://{host}/en-US/{site}{external_path}"

        description_html: str | None = None
        description_text: str | None = None
        employment_type: str | None = None
        try:
            detail = await post_json(client, f"{detail_base}{external_path}", json={})
            if isinstance(detail, dict):
                jp = detail.get("jobPostingInfo") or {}
                description_html = jp.get("jobDescription")
                description_text = html_to_text(description_html)
                employment_type = jp.get("timeType")
                # Workday sometimes returns location as a list of dicts
                if jp.get("location") and not location:
                    location = jp["location"]
        except Exception as e:  # noqa: BLE001
            log.debug("workday_detail_failed", external_id=external_id, error=str(e))

        return RawJob(
            source="workday",
            external_id=external_id,
            title=title.strip(),
            apply_url=apply_url,
            location=location or None,
            country=location or None,
            remote=("remote" in location.lower()) if location else False,
            employment_type=employment_type,
            description_html=description_html,
            description_text=description_text,
            posted_at=parse_dt(posted),
            updated_at_source=parse_dt(posted),
            raw_payload=item,
        )
