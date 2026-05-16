from __future__ import annotations

from app.db.models import Source
from app.scrapers.ashby import AshbyScraper
from app.scrapers.base import BaseScraper
from app.scrapers.bayt import BaytScraper
from app.scrapers.greenhouse import GreenhouseScraper
from app.scrapers.lever import LeverScraper
from app.scrapers.linkedin import LinkedInScraper
from app.scrapers.wellfound import WellfoundScraper
from app.scrapers.workday import WorkdayScraper
from app.scrapers.wuzzuf import WuzzufScraper

_REGISTRY: dict[Source, type[BaseScraper]] = {
    Source.GREENHOUSE: GreenhouseScraper,
    Source.LEVER: LeverScraper,
    Source.ASHBY: AshbyScraper,
    Source.WORKDAY: WorkdayScraper,
    Source.WELLFOUND: WellfoundScraper,
    Source.LINKEDIN: LinkedInScraper,
    Source.WUZZUF: WuzzufScraper,
    Source.BAYT: BaytScraper,
}


def get_scraper(source: Source) -> BaseScraper:
    cls = _REGISTRY.get(source)
    if cls is None:
        raise ValueError(f"No scraper registered for source: {source}")
    return cls()
