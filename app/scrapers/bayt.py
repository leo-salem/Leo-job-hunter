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

log = get_logger(__name__)


class BaytScraper(BaseScraper):
    """Bayt.com — Middle East's largest job board, strong Egypt coverage.

    Config:
        keywords:  str          (e.g. "java", "backend developer")
        location_slug: str      (e.g. "jobs-in-egypt"; defaults to Egypt)
        max_pages: int          (default 5)
    """

    source = "bayt"

    BASE = "https://www.bayt.com"

    async def fetch(self, company: Company) -> Iterable[RawJob]:
        config = company.config or {}
        keywords = config.get("keywords")
        if not keywords:
            raise ScraperError(
                f"bayt: company {company.slug} missing 'keywords' config"
            )

        max_pages = int(config.get("max_pages", 5))
        slug = keywords.strip().lower().replace(" ", "-")

        headers = {
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Referer": "https://www.bayt.com/en/egypt/",
            "Upgrade-Insecure-Requests": "1",
        }

        cards: list[dict] = []
        async with http_client(headers=headers) as client:
            for page in range(1, max_pages + 1):
                url = f"{self.BASE}/en/egypt/jobs/{slug}-jobs/?page={page}"
                try:
                    html = await get_text(client, url)
                except Exception as e:  # noqa: BLE001
                    if page == 1:
                        raise ScraperError(f"bayt list fetch failed for {company.slug}: {e}") from e
                    log.warning("bayt_page_failed", company=company.slug, page=page, error=str(e))
                    break

                page_cards = self._parse_list(html)
                if not page_cards:
                    break
                cards.extend(page_cards)
                await asyncio.sleep(random.uniform(1.0, 2.2))

            # Dedup
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
                    log.debug("bayt_detail_failed", external_id=card["external_id"], error=str(e))
                await asyncio.sleep(random.uniform(0.4, 1.0))

                loc = card.get("location") or "Egypt"
                results.append(
                    RawJob(
                        source="bayt",
                        external_id=card["external_id"],
                        title=card["title"],
                        apply_url=card["apply_url"],
                        location=loc,
                        country=loc,
                        remote=("remote" in loc.lower()),
                        description_html=desc_html,
                        description_text=desc_text,
                        raw_payload={
                            "company_name": card.get("company_name"),
                            "search_keywords": keywords,
                        },
                    )
                )
            return results

    def _parse_list(self, html: str) -> list[dict]:
        """Find job links by href shape — robust against class-name churn."""
        soup = BeautifulSoup(html, "lxml")
        cards: list[dict] = []
        seen: set[str] = set()

        for link in soup.find_all("a", href=re.compile(r"^/en/[^/]+/jobs/[^/?#]+-\d+/?$")):
            href = link.get("href")
            if not href:
                continue
            apply_url = f"{self.BASE}{href}"
            m = re.search(r"-(\d+)/?$", href)
            if not m:
                continue
            external_id = f"bayt-{m.group(1)}"
            if external_id in seen:
                continue
            seen.add(external_id)

            title = link.get_text(strip=True)
            if not title or len(title) < 4:
                # Sometimes the link wraps an icon only — find a sibling h2
                h2 = link.find_parent().find("h2") if link.find_parent() else None
                title = h2.get_text(strip=True) if h2 else title
            if not title:
                continue

            # Walk up for context
            card = link
            for _ in range(6):
                if card.parent is None:
                    break
                card = card.parent

            # Company name: usually a <b> or another <a> with /en/{x}/companies/...
            comp_el = card.find("a", href=re.compile(r"/companies/")) if card else None
            company_name = comp_el.get_text(strip=True) if comp_el else None

            location = None
            if card:
                for s in card.stripped_strings:
                    sl = s.lower()
                    if any(kw in sl for kw in ("cairo", "egypt", "giza", "alexandria", "remote", "mansoura", "tanta")):
                        location = s
                        break

            cards.append(
                {
                    "external_id": external_id,
                    "title": title,
                    "company_name": company_name,
                    "location": location,
                    "apply_url": apply_url,
                }
            )
        return cards

    def _parse_detail(self, html: str) -> tuple[str | None, str | None]:
        soup = BeautifulSoup(html, "lxml")
        desc_div = (
            soup.find("div", class_=re.compile(r"job-description|details-section"))
            or soup.find("section", class_=re.compile(r"card-content"))
            or soup.find("div", attrs={"itemprop": "description"})
        )
        if not desc_div:
            return None, None
        desc_html = str(desc_div)
        return desc_html, html_to_text(desc_html)
