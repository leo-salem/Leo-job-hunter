from __future__ import annotations

import asyncio
import random
import re
from typing import Iterable
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from app.db.models import Company
from app.logging_setup import get_logger
from app.schemas.job import RawJob
from app.scrapers.base import BaseScraper, ScraperError, html_to_text
from app.pipeline.filters import title_matches
from app.utils.hashing import fingerprint
from app.utils.http import get_text, http_client
from app.utils.time import parse_dt

log = get_logger(__name__)


class LinkedInScraper(BaseScraper):
    """LinkedIn jobs via the public guest-search endpoint (no login required).

    Each Company row represents a single saved search. Config:
        keywords:  str       (e.g. "java developer")
        location:  str       (e.g. "Egypt", "Cairo, Egypt")
        time_posted: str     (optional: "r604800" past week, "r86400" past 24h, "r2592000" past month)
        max_pages: int       (default 5 = up to 125 results; cap to be polite)
        fetch_details: bool  (default True — pulls full description per job)
    """

    source = "linkedin"

    SEARCH_URL = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    )
    DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

    async def fetch(
        self, company: Company, *, skip_fingerprints: set[str] | None = None
    ) -> Iterable[RawJob]:
        skip = skip_fingerprints or set()
        config = company.config or {}
        keywords = config.get("keywords")
        location = config.get("location")
        if not (keywords and location):
            raise ScraperError(
                f"linkedin: company {company.slug} missing 'keywords' or 'location' config"
            )

        time_posted = config.get("time_posted", "r604800")  # past 7 days by default
        max_pages = int(config.get("max_pages", 5))
        page_size = 25  # LinkedIn fixed page size
        fetch_details = bool(config.get("fetch_details", True))

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.linkedin.com/jobs/search/",
        }

        cards: list[dict] = []
        async with http_client(headers=headers) as client:
            for page_idx in range(max_pages):
                params = {
                    "keywords": keywords,
                    "location": location,
                    "f_TPR": time_posted,
                    "start": page_idx * page_size,
                }
                url = f"{self.SEARCH_URL}?{urlencode(params)}"
                try:
                    html = await get_text(client, url)
                except Exception as e:  # noqa: BLE001
                    if page_idx == 0:
                        raise ScraperError(
                            f"linkedin: list fetch failed for {company.slug}: {e}"
                        ) from e
                    log.warning(
                        "linkedin_page_failed",
                        company=company.slug,
                        page=page_idx,
                        error=str(e),
                    )
                    break

                page_cards = self._parse_list(html)
                if not page_cards:
                    break
                cards.extend(page_cards)

                # Polite jittered delay between paginated requests
                await asyncio.sleep(random.uniform(1.2, 2.8))

            # Deduplicate by job_id within this run
            seen: set[str] = set()
            unique_cards = []
            for c in cards:
                if c["external_id"] not in seen:
                    seen.add(c["external_id"])
                    unique_cards.append(c)

            results: list[RawJob] = []
            skipped_known = 0
            skipped_title = 0
            for card in unique_cards:
                # OPTIMIZATION 1: skip cards whose title clearly doesn't match
                # the job filter. Avoids paying the ~1s polite detail-fetch
                # cost for jobs the pipeline would discard anyway.
                if not title_matches(card["title"]):
                    skipped_title += 1
                    continue

                # OPTIMIZATION 2: if this job already exists in the DB, emit
                # a stub card so the orchestrator still touches last_seen_at
                # without re-paying for detail fetch.
                card_fp = fingerprint("linkedin", card["external_id"])
                already_known = card_fp in skip

                desc_html = None
                desc_text = None
                if fetch_details and not already_known:
                    try:
                        detail_html = await get_text(
                            client, self.DETAIL_URL.format(job_id=card["external_id"])
                        )
                        desc_html, desc_text = self._parse_detail(detail_html)
                    except Exception as e:  # noqa: BLE001
                        log.debug(
                            "linkedin_detail_failed",
                            company=company.slug,
                            job_id=card["external_id"],
                            error=str(e),
                        )
                    await asyncio.sleep(random.uniform(0.6, 1.5))
                elif already_known:
                    skipped_known += 1

                results.append(
                    RawJob(
                        source="linkedin",
                        external_id=card["external_id"],
                        title=card["title"],
                        apply_url=card["apply_url"],
                        location=card.get("location"),
                        country=card.get("location"),
                        remote=("remote" in (card.get("location") or "").lower()),
                        description_html=desc_html,
                        description_text=desc_text,
                        posted_at=card.get("posted_at"),
                        updated_at_source=card.get("posted_at"),
                        raw_payload={
                            "company_name": card.get("company_name"),
                            "search_keywords": keywords,
                            "search_location": location,
                        },
                    )
                )

            log.info(
                "linkedin_fetch_done",
                company=company.slug,
                total_cards=len(unique_cards),
                accepted=len(results),
                skipped_by_title=skipped_title,
                skipped_known=skipped_known,
            )
            return results

    def _parse_list(self, html: str) -> list[dict]:
        """Parse the seeMoreJobPostings/search HTML response into card dicts."""
        soup = BeautifulSoup(html, "lxml")
        cards: list[dict] = []

        # LinkedIn cards: <li><div class="base-search-card" data-entity-urn="urn:li:jobPosting:NNNNN">
        for li in soup.find_all("li"):
            card_div = li.find("div", class_=re.compile(r"base-search-card|base-card"))
            if not card_div:
                continue
            entity_urn = card_div.get("data-entity-urn") or ""
            m = re.search(r"jobPosting:(\d+)", entity_urn)
            if not m:
                # Fallback: hidden input or tracking-id
                a = card_div.find("a", class_=re.compile(r"base-card__full-link|base-search-card__link"))
                href = a.get("href") if a else ""
                m2 = re.search(r"/jobs/view/[^/?]*-(\d+)(?:\?|$)", href or "")
                if not m2:
                    continue
                job_id = m2.group(1)
            else:
                job_id = m.group(1)

            title_el = card_div.find(class_=re.compile(r"base-search-card__title"))
            title = title_el.get_text(strip=True) if title_el else None

            company_el = card_div.find(class_=re.compile(r"base-search-card__subtitle"))
            company_name = company_el.get_text(strip=True) if company_el else None

            loc_el = card_div.find(class_=re.compile(r"job-search-card__location"))
            location = loc_el.get_text(strip=True) if loc_el else None

            link_el = card_div.find("a", class_=re.compile(r"base-card__full-link|base-search-card__link"))
            apply_url = link_el.get("href").split("?")[0] if link_el and link_el.get("href") else (
                f"https://www.linkedin.com/jobs/view/{job_id}"
            )

            time_el = card_div.find("time")
            posted_at = None
            if time_el:
                dt = time_el.get("datetime")
                if dt:
                    posted_at = parse_dt(dt)

            if not title:
                continue

            cards.append(
                {
                    "external_id": job_id,
                    "title": title,
                    "company_name": company_name,
                    "location": location,
                    "apply_url": apply_url,
                    "posted_at": posted_at,
                }
            )
        return cards

    def _parse_detail(self, html: str) -> tuple[str | None, str | None]:
        soup = BeautifulSoup(html, "lxml")
        desc_div = soup.find(class_=re.compile(r"show-more-less-html__markup|description__text"))
        if not desc_div:
            return None, None
        desc_html = str(desc_div)
        return desc_html, html_to_text(desc_html)
