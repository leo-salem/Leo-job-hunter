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
from app.utils.http import get_text, http_client
from app.utils.time import parse_dt

log = get_logger(__name__)


class WuzzufScraper(BaseScraper):
    """Wuzzuf.net — Egypt's largest job board.

    Each Company row is a saved search. Config:
        keywords:    str    (e.g. "java backend")
        country:     str    (default "Egypt"; Wuzzuf is mostly Egypt anyway)
        max_pages:   int    (default 5 = up to ~75 jobs)
        years_min:   int    (optional, default 0)
        years_max:   int    (optional, default 2)
    """

    source = "wuzzuf"

    SEARCH_URL = "https://wuzzuf.net/search/jobs/"

    async def fetch(self, company: Company) -> Iterable[RawJob]:
        config = company.config or {}
        keywords = config.get("keywords") or ""
        if not keywords:
            raise ScraperError(
                f"wuzzuf: company {company.slug} missing 'keywords' config"
            )

        max_pages = int(config.get("max_pages", 6))

        # Browser-like headers — Wuzzuf 500s on requests that look too API-ish
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Referer": "https://wuzzuf.net/jobs/egypt",
            "Upgrade-Insecure-Requests": "1",
        }

        cards: list[dict] = []
        async with http_client(headers=headers) as client:
            for page in range(max_pages):
                # Minimal param set — years/country filters were causing 500s.
                # Wuzzuf is Egypt-dominant anyway; we further filter by title in the pipeline.
                params = {"q": keywords, "start": page}
                url = f"{self.SEARCH_URL}?{urlencode(params)}"
                try:
                    html = await get_text(client, url)
                except Exception as e:  # noqa: BLE001
                    if page == 0:
                        raise ScraperError(
                            f"wuzzuf list fetch failed for {company.slug}: {e}"
                        ) from e
                    log.warning("wuzzuf_page_failed", company=company.slug, page=page, error=str(e))
                    break

                page_cards = self._parse_list(html)
                if not page_cards:
                    break
                cards.extend(page_cards)
                await asyncio.sleep(random.uniform(1.0, 2.2))

            # Dedup by external_id
            seen: set[str] = set()
            unique_cards = [c for c in cards if not (c["external_id"] in seen or seen.add(c["external_id"]))]

            results: list[RawJob] = []
            for card in unique_cards:
                desc_html = None
                desc_text = None
                try:
                    detail_html = await get_text(client, card["apply_url"])
                    desc_html, desc_text = self._parse_detail(detail_html)
                except Exception as e:  # noqa: BLE001
                    log.debug(
                        "wuzzuf_detail_failed",
                        company=company.slug,
                        job_id=card["external_id"],
                        error=str(e),
                    )
                await asyncio.sleep(random.uniform(0.4, 1.0))

                results.append(
                    RawJob(
                        source="wuzzuf",
                        external_id=card["external_id"],
                        title=card["title"],
                        apply_url=card["apply_url"],
                        location=card.get("location") or "Egypt",
                        country=card.get("location") or "Egypt",
                        remote=("remote" in (card.get("location") or "").lower()),
                        description_html=desc_html,
                        description_text=desc_text,
                        posted_at=card.get("posted_at"),
                        updated_at_source=card.get("posted_at"),
                        raw_payload={
                            "company_name": card.get("company_name"),
                            "search_keywords": keywords,
                        },
                    )
                )
            return results

    def _parse_list(self, html: str) -> list[dict]:
        """Robust parser — finds job links by href shape rather than CSS class,
        since Wuzzuf's class names are hashed/obfuscated and change frequently."""
        soup = BeautifulSoup(html, "lxml")
        cards: list[dict] = []
        seen: set[str] = set()

        for link in soup.find_all("a", href=re.compile(r"^/jobs/p/")):
            href = link.get("href")
            if not href:
                continue
            apply_url = f"https://wuzzuf.net{href}"
            m = re.search(r"/jobs/p/([^/?#]+)", href)
            if not m:
                continue
            external_id = m.group(1)
            if external_id in seen:
                continue
            seen.add(external_id)

            title = link.get_text(strip=True)
            if not title:
                continue

            # Walk up to the enclosing card for company+location context
            card = link
            for _ in range(6):
                if card.parent is None:
                    break
                card = card.parent

            comp_el = card.find("a", href=re.compile(r"^/jobs/companies/")) if card else None
            company_name = comp_el.get_text(strip=True) if comp_el else None

            location = None
            if card:
                # Look for any text node that mentions an Egypt location
                for s in card.stripped_strings:
                    sl = s.lower()
                    if any(kw in sl for kw in ("cairo", "egypt", "giza", "alexandria", "remote")):
                        location = s
                        break

            cards.append(
                {
                    "external_id": external_id,
                    "title": title,
                    "company_name": company_name,
                    "location": location,
                    "apply_url": apply_url,
                    "posted_at": None,
                }
            )
        return cards

    def _parse_detail(self, html: str) -> tuple[str | None, str | None]:
        soup = BeautifulSoup(html, "lxml")
        desc_div = soup.find("div", class_=re.compile(r"css-1uobp1k|e1tkpvjy0|job-description"))
        if not desc_div:
            # Fallback: take the main job content section
            desc_div = soup.find("section", class_=re.compile(r"css-ssjg3"))
        if not desc_div:
            return None, None
        desc_html = str(desc_div)
        return desc_html, html_to_text(desc_html)
