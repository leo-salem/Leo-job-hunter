from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Iterable

from bs4 import BeautifulSoup

from app.db.models import Company
from app.schemas.job import RawJob


_WS_RE = re.compile(r"\s+")


def html_to_text(html: str | None) -> str | None:
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator="\n")
    text = _WS_RE.sub(" ", text)
    return text.strip() or None


class ScraperError(Exception):
    """Raised by scrapers for any expected, recoverable failure."""


class BaseScraper(ABC):
    source: str = ""

    @abstractmethod
    async def fetch(self, company: Company) -> Iterable[RawJob]:
        """Yield/return all currently-listed jobs for a company.

        Implementations must NOT raise on partial failures inside the page —
        log them and continue. They MAY raise ScraperError for total failure.
        """
