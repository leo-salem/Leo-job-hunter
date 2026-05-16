from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Iterable

from app.config import settings
from app.db.models import Company
from app.logging_setup import get_logger
from app.schemas.job import RawJob
from app.scrapers.base import BaseScraper, ScraperError, html_to_text

log = get_logger(__name__)


class WellfoundScraper(BaseScraper):
    """Best-effort Wellfound scraper using Playwright.

    Disabled by default (WELLFOUND_ENABLED=false). Heavy Cloudflare anti-bot
    means this scraper may break or require manual cookie refresh. It will
    NEVER crash the daily run — failure is logged and the rest of the pipeline
    continues.

    Cookies are persisted to ./data/wellfound_state.json so that a one-time
    manual browser session (run headed) can be reused by subsequent runs.
    """

    source = "wellfound"

    LIST_URL = (
        "https://wellfound.com/jobs?roles[]=Software+Engineer&"
        "roles[]=Backend+Engineer&yearsExperience[]=0-2&yearsExperience[]=2-4"
    )

    async def fetch(self, company: Company) -> Iterable[RawJob]:
        if not settings.wellfound_enabled:
            log.info("wellfound_disabled", company=company.slug)
            return []

        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise ScraperError("playwright not installed") from e

        state_path = settings.project_root / "data" / "wellfound_state.json"
        state_path.parent.mkdir(exist_ok=True)

        results: list[RawJob] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.playwright_headless)
            context_kwargs: dict = {
                "user_agent": settings.http_user_agent,
                "viewport": {"width": 1280, "height": 800},
            }
            if state_path.exists():
                context_kwargs["storage_state"] = str(state_path)
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

            try:
                await page.goto(self.LIST_URL, wait_until="domcontentloaded", timeout=45000)
                # Detect Cloudflare interstitial / login wall
                title = (await page.title()) or ""
                if "Just a moment" in title or "Attention Required" in title:
                    raise ScraperError("wellfound: blocked by Cloudflare")

                # Scroll a few times to load lazy results
                for _ in range(5):
                    await page.mouse.wheel(0, 1500)
                    await asyncio.sleep(1.2)

                html = await page.content()
                results = self._parse_listing(html)

                # Persist cookies for next run
                await context.storage_state(path=str(state_path))
            except ScraperError:
                raise
            except Exception as e:  # noqa: BLE001
                # Save a screenshot for debugging
                shot_path = settings.project_root / "data" / "wellfound_error.png"
                try:
                    await page.screenshot(path=str(shot_path), full_page=True)
                except Exception:  # noqa: BLE001
                    pass
                raise ScraperError(f"wellfound playwright failure: {e}") from e
            finally:
                await context.close()
                await browser.close()

        return results

    def _parse_listing(self, html: str) -> list[RawJob]:
        """Extract jobs from the Next.js __NEXT_DATA__ JSON blob.

        Falls back to an empty list if structure has shifted. This is brittle by
        design — Wellfound restructures their app periodically.
        """
        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not m:
            log.warning("wellfound_no_next_data")
            return []
        try:
            blob = json.loads(m.group(1))
        except json.JSONDecodeError:
            log.warning("wellfound_next_data_parse_failed")
            return []

        # Walk the blob for any list-like structure containing job-shaped dicts.
        out: list[RawJob] = []
        for candidate in _iter_dicts(blob):
            if not isinstance(candidate, dict):
                continue
            jid = candidate.get("id") or candidate.get("jobId")
            title = candidate.get("title")
            slug = candidate.get("slug") or candidate.get("jobSlug")
            company = candidate.get("startupName") or (
                candidate.get("startup", {}) or {}
            ).get("name")
            if not (jid and title and (slug or candidate.get("publicId"))):
                continue
            apply_url = (
                candidate.get("jobUrl")
                or (f"https://wellfound.com/jobs/{slug}" if slug else "")
                or (f"https://wellfound.com/jobs/{candidate.get('publicId')}")
            )
            description_html = candidate.get("description") or candidate.get("jobDescription")
            location = candidate.get("locations") or candidate.get("location") or ""
            if isinstance(location, list):
                location = ", ".join(str(x) for x in location if x)
            remote = bool(candidate.get("remote") or "remote" in (location or "").lower())

            out.append(
                RawJob(
                    source="wellfound",
                    external_id=str(jid),
                    title=str(title).strip(),
                    apply_url=apply_url,
                    location=location or None,
                    country=location or None,
                    remote=remote,
                    description_html=description_html,
                    description_text=html_to_text(description_html),
                    raw_payload={"company": company, "id": jid},
                )
            )
        return out


def _iter_dicts(obj):
    """Recursively yield every dict found inside a nested structure."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _iter_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_dicts(v)
