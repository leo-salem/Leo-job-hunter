"""Regex banks for the upgraded scoring engine.

Each constant is a category of phrases. Rules in `scoring_rules.py` count how
many phrases from each bank are present in the description; the count maps to
a small bonus or penalty. This keeps the rule code clean and the lexicon
easy to tune in one place.
"""
from __future__ import annotations

import re


def _any(*patterns: str) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


# --- Visa / relocation (INTERNATIONAL boost) ---
VISA_PHRASES = _any(
    r"visa\s+sponsor(ship)?",
    r"sponsor(s|ing|ship)?\s+(visa|work\s+permit|immigration)",
    r"relocation\s+(support|package|assistance|bonus|provided|offered)",
    r"relocate\s+(you|candidates?)\s+to",
    r"international\s+(candidates|applicants|hire)",
    r"global\s+(hiring|talent\s+pool)",
    r"work\s+authorization\s+(support|sponsor)",
    r"immigration\s+(support|assistance|sponsor)",
    r"h1[- ]?b\s+(sponsor|transfer)",
    r"willing\s+to\s+relocate",
)

# --- Modern engineering / scale signals (INTERNATIONAL boost) ---
SCALE_PHRASES = _any(
    r"distributed\s+systems?",
    r"high[- ]scale",
    r"high[- ]throughput",
    r"low[- ]latency",
    r"millions?\s+of\s+(users|requests|events|records)",
    r"billions?\s+of\s+(users|requests|events|records)",
    r"petabyte",
    r"event[- ]driven\s+(architecture|systems?)",
    r"service[- ]oriented\s+architecture",
    r"horizontally\s+scal",
    r"system\s+design",
    r"scal(e|ability|able)\s+(challenges?|problems?)",
)

PLATFORM_PHRASES = _any(
    r"platform\s+(engineer|engineering|team)",
    r"infrastructure\s+(team|platform|engineer|engineering)",
    r"developer\s+(platform|productivity|experience|tools)",
    r"internal\s+(platform|developer\s+tools)",
    r"api\s+(platform|gateway|design|at\s+scale)",
    r"backend\s+(platform|services|infrastructure)",
    r"cloud[- ]native",
    r"observability",
    r"reliability\s+engineering",
    r"performance\s+engineering",
    r"ci/cd",
    r"continuous\s+(integration|deployment|delivery)",
)

# --- Career growth (INTERNATIONAL + EGYPT boost) ---
GROWTH_PHRASES = _any(
    r"mentor(ship|ing|s)?",
    r"learning\s+(opportunit|culture|environment|stipend|budget)",
    r"career\s+(growth|development|progression|path)",
    r"engineering\s+(culture|excellence|practices)",
    r"ownership",
    r"rotational\s+program",
    r"graduate\s+program",
    r"new\s+grad\s+program",
    r"trainee\s+program",
    r"continuous\s+learning",
    r"growth\s+mindset",
    r"professional\s+development",
    r"conference\s+budget",
)

# --- IT support / maintenance / low-eng signals (PENALTIES) ---
SUPPORT_MAINT_PHRASES = _any(
    r"help\s?desk",
    r"it\s+support",
    r"technical\s+support",
    r"tier\s+[12]\s+support",
    r"l[12]\s+support",
    r"on[- ]call\s+(rotation\s+heavy|24/7)",
    r"end[- ]user\s+support",
    r"customer\s+support\s+engineer",
)

LEGACY_PHRASES = _any(
    r"legacy\s+(system|code|application|maintenance)",
    r"maintain\s+legacy",
    r"struts\s+\d",
    r"jsp\b",
    r"ejb\b",
    r"weblogic|websphere",
    r"vb\.net|vb6",
    r"cobol",
    r"mainframe",
    r"perl\b",
)

LOW_ENG_PHRASES = _any(
    r"wordpress",
    r"drupal",
    r"shopify\s+theme",
    r"squarespace",
    r"low[- ]code",
    r"no[- ]code",
    r"cms\s+(admin|maintenance)",
    r"sharepoint\s+admin",
    r"data\s+entry",
)

# --- "Engineering-heavy generic SWE" qualifiers (used as a gate) ---
ENG_HEAVY_PHRASES = _any(
    r"distributed\s+system",
    r"backend\s+service",
    r"api\b",
    r"microservic",
    r"infrastructure",
    r"high[- ]scale",
    r"cloud[- ]native",
    r"kubernetes|\bk8s\b",
    r"event[- ]driven",
    r"data\s+pipeline",
    r"streaming",
    r"low[- ]latency",
)

# --- Anti-spam / quality-loss signals ---
SPAM_PHRASES = _any(
    r"urgent(ly)?\s+hiring",
    r"immediate\s+joiner",
    r"apply\s+now\s+!!!",
    r"!!!+",
    r"contact\s+us\s+(asap|immediately)",
    r"send\s+(your\s+)?cv\s+to\s+[a-z0-9_.+-]+@",
    r"whatsapp\s+(us\s+)?(at|on)\s+\+?\d",
    r"send\s+(an\s+)?email\s+at\s+[a-z0-9_.+-]+@",
)

# --- Buzzword stuffing (multiple = lower quality) ---
BUZZWORDS = _any(
    r"\brockstar\b",
    r"\bninja\b",
    r"\bguru\b",
    r"\bpassionate\b",
    r"\bself[- ]starter\b",
    r"\bgame[- ]?changer\b",
    r"\bdisruptive\b",
    r"\bsynergy\b",
    r"\bvisionary\b",
    r"\bdynamic\s+(person|individual|team\s+player)\b",
)
