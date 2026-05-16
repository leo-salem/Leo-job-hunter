from __future__ import annotations

import re

from app.db.models import Region
from app.schemas.job import RawJob

# --- Title matchers ---
_INCLUDE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bsoftware\s+engineer\b",
        r"\bsoftware\s+developer\b",
        r"\bbackend\s+(?:software\s+)?(?:engineer|developer)\b",
        r"\bback[- ]end\s+(?:engineer|developer)\b",
        r"\bjava\s+(?:software\s+)?(?:engineer|developer)\b",
        r"\bspring\s+boot\b",
        r"\bjunior\s+(?:software|backend|java)\b",
        r"\bnew\s*grad(?:uate)?\b",
        r"\bentry[- ]level\s+(?:software|backend|engineer|developer)\b",
        r"\bgraduate\s+(?:software|engineer|developer)\b",
        r"\bassociate\s+(?:software\s+)?(?:engineer|developer)\b",
        r"\bsoftware\s+engineer\s+(?:i|1)\b",
    ]
]

_EXCLUDE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\b(senior|sr\.|staff|principal|lead|director|head of|manager|vp|vice president|architect|chief)\b",
        r"\bml\s+engineer\b",
        r"\bmachine\s+learning\b",
        r"\bdata\s+(scientist|engineer)\b",
        r"\bsre\b|\bsite\s+reliability\b",
        r"\bdevops\b",
        r"\bsecurity\s+engineer\b",
        r"\bios\b|\bandroid\b|\bmobile\b",
        r"\bdesigner\b|\bproduct\s+manager\b",
        r"\bqa\b|\btest\s+engineer\b|\bsdet\b",
        r"\bsales\b|\bmarketing\b|\brecruiter\b",
        r"\bintern(ship)?\b",
        r"\bcontract(or)?\b|\bcontract-to-hire\b",
        r"\bfrontend\b|\bfront[- ]end\b|\bfull[- ]stack\b",
    ]
]

# --- Location matchers ---
_USA_TOKENS = {
    "united states", "u.s.", "usa", "us", "remote - us", "remote us", "remote, us",
    "new york", "san francisco", "seattle", "boston", "austin", "chicago", "los angeles",
    "denver", "atlanta", "washington", "miami", "dallas", "houston", "philadelphia",
}

_EUROPE_COUNTRIES = {
    "uk", "united kingdom", "england", "scotland", "wales", "northern ireland",
    "ireland", "germany", "france", "spain", "portugal", "italy", "netherlands",
    "belgium", "luxembourg", "denmark", "sweden", "norway", "finland", "iceland",
    "poland", "czech republic", "czechia", "austria", "switzerland", "hungary",
    "romania", "bulgaria", "greece", "estonia", "latvia", "lithuania", "croatia",
    "slovakia", "slovenia", "serbia", "ukraine", "remote - emea", "emea",
    "remote europe", "europe", "eu",
}

_EGYPT_TOKENS = {
    "egypt", "cairo", "alexandria", "giza", "new cairo", "smart village",
    "maadi", "heliopolis", "nasr city", "sheikh zayed", "october city",
    "6th of october", "mansoura", "tanta",
}


def title_matches(title: str) -> bool:
    if not title:
        return False
    if any(p.search(title) for p in _EXCLUDE_PATTERNS):
        return False
    return any(p.search(title) for p in _INCLUDE_PATTERNS)


def location_matches_international(location: str | None, remote: bool) -> tuple[bool, str | None]:
    """USA / Europe / Remote rules. Returns (passes, normalized_country)."""
    if remote:
        return True, "Remote"
    if not location:
        return False, None
    s = location.lower()
    if any(t in s for t in _USA_TOKENS):
        return True, "USA"
    if any(t in s for t in _EUROPE_COUNTRIES):
        return True, "Europe"
    return False, None


def location_matches_egypt(location: str | None, remote: bool) -> tuple[bool, str | None]:
    """Egypt rules: any Egypt city/region OR remote (since remote Egypt-eligible counts)."""
    if not location:
        # Wuzzuf and LinkedIn-Egypt searches default to Egypt — accept missing locations
        return True, "Egypt"
    s = location.lower()
    if any(t in s for t in _EGYPT_TOKENS):
        return True, "Egypt"
    if remote and any(t in s for t in {"mena", "middle east", "africa", "arab"}):
        return True, "Egypt (Remote)"
    return False, None


def experience_excluded(text: str | None) -> bool:
    """Reject if JD demands 3+ years experience and no junior/new-grad hint."""
    if not text:
        return False
    t = text.lower()
    if re.search(r"\b([3-9]|1[0-9])\+?\s*(years|yrs)\s+of\s+experience\b", t):
        if not re.search(r"\b(new grad|junior|entry[- ]level|0[- ]2\s*years|0[- ]3\s*years)\b", t):
            return True
    return False


def passes_for_region(job: RawJob, region: Region) -> tuple[bool, str | None]:
    """Region-aware filter. Returns (passes, normalized_country)."""
    if not title_matches(job.title):
        return False, None
    if region == Region.EGYPT:
        loc_ok, country = location_matches_egypt(job.location, job.remote)
    else:
        loc_ok, country = location_matches_international(job.location, job.remote)
    if not loc_ok:
        return False, None
    if experience_excluded(job.description_text):
        return False, None
    return True, country


# Backwards-compatible alias (existing imports keep working with default region)
def passes_all(job: RawJob) -> tuple[bool, str | None]:
    return passes_for_region(job, Region.INTERNATIONAL)
