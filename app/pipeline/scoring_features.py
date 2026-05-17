"""Feature extraction: parse a job once into a structured `JobFeatures` object.

All heavy regex work happens here, so the rule evaluators downstream operate on
pre-parsed attributes and stay simple + fast.
"""
from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from datetime import datetime

from app.db.models import Region


# ===== Enums =====

class Seniority(str, enum.Enum):
    UNKNOWN = "unknown"
    INTERN = "intern"
    GRADUATE = "graduate"      # new grad / graduate program
    JUNIOR = "junior"          # junior / entry-level / associate / level-1
    MID = "mid"                # level-2 / no specific seniority words
    SENIOR = "senior"          # senior / sr. / level-3+
    STAFF = "staff"            # staff / principal
    LEAD = "lead"              # lead / manager / director / head / architect


class Specialization(str, enum.Enum):
    UNKNOWN = "unknown"
    GENERIC_SWE = "generic_swe"
    BACKEND = "backend"
    FRONTEND = "frontend"
    FULLSTACK = "fullstack"
    MOBILE = "mobile"
    ML = "ml"
    DATA = "data"
    DEVOPS = "devops"
    QA = "qa"
    SECURITY = "security"
    EMBEDDED = "embedded"
    GAME = "game"


# ===== Stack vocabulary =====

# Each stack token may appear as multiple aliases; we normalize down to one key.
STACK_ALIASES: dict[str, list[str]] = {
    "java":          [r"\bjava\b(?!\s*script)"],
    "spring":        [r"\bspring(?:\s*boot|\s*mvc|\s*cloud|\s*security|\s*data)?\b"],
    "hibernate":     [r"\bhibernate\b"],
    "jpa":           [r"\bjpa\b"],
    "kafka":         [r"\bkafka\b"],
    "rabbitmq":      [r"\brabbit\s*mq\b"],
    "microservices": [r"\bmicroservic", r"\bdistributed\s+system"],
    "redis":         [r"\bredis\b"],
    "postgres":      [r"\bpostgres(?:ql)?\b", r"\bpsql\b"],
    "mysql":         [r"\bmysql\b", r"\bmariadb\b"],
    "mongodb":       [r"\bmongo(?:db)?\b"],
    "docker":        [r"\bdocker\b"],
    "kubernetes":    [r"\bkubernetes\b", r"\bk8s\b"],
    "rest":          [r"\brest\b", r"\brestful\b"],
    "grpc":          [r"\bgrpc\b"],
    "graphql":       [r"\bgraphql\b"],
    "jwt":           [r"\bjwt\b", r"json\s+web\s+token"],
    "oauth":         [r"\boauth\d?\b"],
    "keycloak":      [r"\bkeycloak\b"],
    "aws":           [r"\baws\b|amazon\s+web\s+services"],
    "gcp":           [r"\bgcp\b|google\s+cloud"],
    "azure":         [r"\bazure\b"],
    "terraform":     [r"\bterraform\b"],
    "go":            [r"\bgolang\b|\bgo\s+lang\b|(?<![\w-])go(?=\s+(developer|engineer|programmer))"],
    "python":        [r"\bpython\b"],
    "node":          [r"\bnode\.?js\b|\bnode\b"],
    "react":         [r"\breact(?:\.js)?\b"],
    "vue":           [r"\bvue(?:\.js)?\b"],
    "angular":       [r"\bangular\b"],
    "typescript":    [r"\btypescript\b|\bts\b(?!\s*-)"],
    "kotlin":        [r"\bkotlin\b"],
    "scala":         [r"\bscala\b"],
    "rust":          [r"\brust\b"],
    "ruby":          [r"\bruby\b|\brails\b"],
    "csharp":        [r"\bc#\b|\b\.net\b|asp\.net"],
    "swift":         [r"\bswift\b|\biOS\b|\bobjective-?c\b"],
    "android":       [r"\bandroid\b"],
}

STACK_COMPILED = {
    key: [re.compile(p, re.IGNORECASE) for p in pats]
    for key, pats in STACK_ALIASES.items()
}

# Coherent backend Java stack (synergy bonus when many co-occur)
JAVA_BACKEND_CORE = {"java", "spring", "hibernate", "jpa", "rest"}
MODERN_BACKEND_CORE = {"docker", "kubernetes", "microservices", "postgres", "redis", "kafka", "rest", "grpc"}
FRONTEND_HEAVY = {"react", "vue", "angular", "typescript"}
NON_JAVA_BACKEND_LANGS = {"go", "node", "python", "ruby", "rust", "csharp", "scala"}


# ===== Title normalization =====

_TITLE_ABBREVIATIONS = [
    (re.compile(r"\bswe\b", re.IGNORECASE), "software engineer"),
    (re.compile(r"\bsde\b", re.IGNORECASE), "software engineer"),
    (re.compile(r"\bsse\b", re.IGNORECASE), "software engineer"),
    (re.compile(r"\bjr\b\.?", re.IGNORECASE), "junior"),
    (re.compile(r"\bsr\b\.?", re.IGNORECASE), "senior"),
    (re.compile(r"\bassoc\b\.?", re.IGNORECASE), "associate"),
    (re.compile(r"\beng\b\.?", re.IGNORECASE), "engineer"),
    (re.compile(r"\bdev\b\.?", re.IGNORECASE), "developer"),
    (re.compile(r"\bmgr\b\.?", re.IGNORECASE), "manager"),
]

_LEVEL_ROMAN_TO_DIGIT = [
    (re.compile(r"\b(engineer|developer|swe|sde)\s+i\b", re.IGNORECASE), r"\1 1"),
    (re.compile(r"\b(engineer|developer|swe|sde)\s+ii\b", re.IGNORECASE), r"\1 2"),
    (re.compile(r"\b(engineer|developer|swe|sde)\s+iii\b", re.IGNORECASE), r"\1 3"),
    (re.compile(r"\b(engineer|developer|swe|sde)\s+iv\b", re.IGNORECASE), r"\1 4"),
]


def normalize_title(raw: str) -> str:
    t = (raw or "").strip()
    for pat, repl in _LEVEL_ROMAN_TO_DIGIT:
        t = pat.sub(repl, t)
    for pat, repl in _TITLE_ABBREVIATIONS:
        t = pat.sub(repl, t)
    # Collapse whitespace, dashes, parens content
    t = re.sub(r"[\(\)\[\]]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip().lower()


# ===== Seniority detection =====

_SENIORITY_PATTERNS: list[tuple[Seniority, re.Pattern[str]]] = [
    (Seniority.INTERN,   re.compile(r"\b(intern(ship)?|trainee)\b")),
    (Seniority.STAFF,    re.compile(r"\b(staff|principal|distinguished)\b")),
    (Seniority.LEAD,     re.compile(r"\b(lead|head\s+of|director|architect|manager|chief|vp|vice\s+president)\b")),
    (Seniority.SENIOR,   re.compile(r"\bsenior\b|(?:engineer|developer)\s+(?:3|4|iii|iv)\b")),
    (Seniority.GRADUATE, re.compile(r"\b(new\s+grad(uate)?|graduate\s+(?:software|engineer|developer|program))\b")),
    (Seniority.JUNIOR,   re.compile(r"\b(junior|entry[- ]?level|associate)\b|(?:engineer|developer)\s+(?:1|i)\b")),
    (Seniority.MID,      re.compile(r"\b(mid[- ]?level|intermediate)\b|(?:engineer|developer)\s+(?:2|ii)\b")),
]


def detect_seniority(title_norm: str, description_text: str, required_years: int | None) -> Seniority:
    """Title patterns dominate. Description-derived years are a fallback."""
    for level, pat in _SENIORITY_PATTERNS:
        if pat.search(title_norm):
            return level
    # Fallback: infer from years-of-experience
    if required_years is not None:
        if required_years >= 7:
            return Seniority.STAFF
        if required_years >= 5:
            return Seniority.SENIOR
        if required_years >= 3:
            return Seniority.MID
        if required_years <= 2:
            return Seniority.JUNIOR
    # Look at description for explicit graduate-program wording
    if re.search(r"\b(graduate\s+programme?|new\s+grad)\b", description_text, re.IGNORECASE):
        return Seniority.GRADUATE
    return Seniority.UNKNOWN


# ===== Specialization detection =====

_SPECIALIZATION_PATTERNS: list[tuple[Specialization, re.Pattern[str]]] = [
    # Order matters — most-specific first
    (Specialization.ML,        re.compile(r"\b(ml\s+engineer|machine\s+learning|deep\s+learning|nlp\s+engineer|llm\s+engineer)\b")),
    (Specialization.DATA,      re.compile(r"\bdata\s+(scientist|engineer|analyst|architect)\b")),
    (Specialization.DEVOPS,    re.compile(r"\b(devops|sre|site\s+reliability|platform\s+engineer|infrastructure\s+engineer|cloud\s+engineer)\b")),
    (Specialization.QA,        re.compile(r"\b(qa|quality|test\s+engineer|sdet|automation\s+engineer)\b")),
    (Specialization.SECURITY,  re.compile(r"\b(security\s+engineer|appsec|infosec|cybersecurity)\b")),
    (Specialization.MOBILE,    re.compile(r"\b(mobile|ios|android|flutter|react\s+native|swift\s+developer|kotlin\s+(developer|engineer))\b")),
    (Specialization.EMBEDDED,  re.compile(r"\b(embedded|firmware|driver\s+developer)\b")),
    (Specialization.GAME,      re.compile(r"\bgame(\s+(developer|engineer|programmer))\b|\bunity\s+developer\b|\bunreal\b")),
    (Specialization.FRONTEND,  re.compile(r"\bfront[- ]?end\b|\bfrontend\b|\bui\s+(developer|engineer)\b")),
    (Specialization.FULLSTACK, re.compile(r"\bfull[- ]?stack\b|\bfullstack\b")),
    (Specialization.BACKEND,   re.compile(r"\bback[- ]?end\b|\bbackend\b|\bapi\s+(developer|engineer)\b|\bserver[- ]side\b")),
    (Specialization.GENERIC_SWE, re.compile(r"\bsoftware\s+(engineer|developer)\b|\bprogrammer\b")),
]


def detect_specialization(title_norm: str) -> Specialization:
    for spec, pat in _SPECIALIZATION_PATTERNS:
        if pat.search(title_norm):
            return spec
    return Specialization.UNKNOWN


# ===== Experience extraction =====

_YEARS_HARD = re.compile(
    r"(?:minimum|min\.?|at\s+least|must\s+have|required|requires?)\s+(?:of\s+)?(\d{1,2})\+?\s*(?:years|yrs)",
    re.IGNORECASE,
)
_YEARS_SOFT = re.compile(
    r"(?:preferred|ideal(?:ly)?|nice\s+to\s+have|bonus(?:\s+points)?|plus|advantage)\s*(?:[:,]?\s*)?(\d{1,2})\+?\s*(?:years|yrs)",
    re.IGNORECASE,
)
_YEARS_GENERIC = re.compile(r"\b(\d{1,2})\+?\s*(?:years|yrs)\s+of\s+(?:experience|exp)\b", re.IGNORECASE)
_YEARS_RANGE = re.compile(r"\b(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:years|yrs)\b", re.IGNORECASE)


@dataclass
class ExperienceSignal:
    required_years: int | None = None     # hard requirement (e.g. "must have 5+ yrs")
    preferred_years: int | None = None    # soft requirement
    range_min: int | None = None
    range_max: int | None = None
    has_grad_friendly_phrase: bool = False  # "no experience required", "0-2 years", "new grad welcome"


_GRAD_FRIENDLY = re.compile(
    r"\b(0\s*[-–]\s*[12]\s*(years|yrs)|no\s+(prior\s+)?(professional\s+)?experience\s+required|new\s+grads?\s+welcome|recent\s+graduate|fresh\s+graduate|entry[- ]?level)\b",
    re.IGNORECASE,
)


def extract_experience(text: str) -> ExperienceSignal:
    out = ExperienceSignal()
    if not text:
        return out

    if m := _YEARS_HARD.search(text):
        out.required_years = int(m.group(1))
    if m := _YEARS_SOFT.search(text):
        out.preferred_years = int(m.group(1))
    if m := _YEARS_RANGE.search(text):
        out.range_min = int(m.group(1))
        out.range_max = int(m.group(2))
    if out.required_years is None and out.preferred_years is None and out.range_min is None:
        if m := _YEARS_GENERIC.search(text):
            # Generic "5+ years of experience" — treat as required
            out.required_years = int(m.group(1))

    out.has_grad_friendly_phrase = bool(_GRAD_FRIENDLY.search(text))
    return out


# ===== Skill mention with required/preferred context =====

@dataclass
class SkillMention:
    skill: str
    in_title: bool = False
    in_description: bool = False
    is_required: bool = False
    is_preferred: bool = False


def detect_stack(title_norm: str, description_text: str) -> dict[str, SkillMention]:
    """Return a dict {skill -> SkillMention} for every detected skill."""
    desc_lower = (description_text or "").lower()
    out: dict[str, SkillMention] = {}

    # Pre-extract "Preferred / Nice to have" sections for context tagging
    pref_section = _extract_section(
        desc_lower,
        keywords=("nice to have", "preferred", "bonus", "plus", "advantage", "good to have"),
    )
    req_section = _extract_section(
        desc_lower,
        keywords=("requirements", "must have", "qualifications", "required skills", "you have", "what we need"),
    )

    for skill, patterns in STACK_COMPILED.items():
        in_title = any(p.search(title_norm) for p in patterns)
        in_desc = any(p.search(desc_lower) for p in patterns)
        if not (in_title or in_desc):
            continue
        is_pref = bool(pref_section) and any(p.search(pref_section) for p in patterns)
        is_req = bool(req_section) and any(p.search(req_section) for p in patterns)
        if is_pref and not is_req:
            # If skill ONLY appears in preferred section, tag as preferred
            out[skill] = SkillMention(skill, in_title, in_desc, is_required=False, is_preferred=True)
        else:
            out[skill] = SkillMention(skill, in_title, in_desc, is_required=is_req or in_title, is_preferred=False)
    return out


def _extract_section(text: str, *, keywords: tuple[str, ...]) -> str:
    """Naive but useful: return the first ~500 chars following any keyword
    that marks a section heading."""
    lo = text.lower()
    earliest = -1
    for kw in keywords:
        idx = lo.find(kw)
        if idx != -1 and (earliest == -1 or idx < earliest):
            earliest = idx
    if earliest == -1:
        return ""
    return text[earliest : earliest + 800]


# ===== Job features (the consolidated output of preprocessing) =====

@dataclass
class JobFeatures:
    title_raw: str
    title_norm: str
    description_text: str

    seniority: Seniority
    specialization: Specialization
    stack: dict[str, SkillMention]
    experience: ExperienceSignal

    remote: bool
    country: str | None
    region: Region
    posted_at: datetime | None
    company_name: str | None
    source: str

    # Cached convenience views
    stack_keys: set[str] = field(init=False)
    stack_in_title_keys: set[str] = field(init=False)
    description_chars: int = field(init=False)

    def __post_init__(self) -> None:
        self.stack_keys = set(self.stack)
        self.stack_in_title_keys = {k for k, m in self.stack.items() if m.in_title}
        self.description_chars = len(self.description_text or "")


def build_features(
    *,
    title: str,
    description_text: str | None,
    remote: bool,
    country: str | None,
    region: Region,
    posted_at: datetime | None = None,
    company_name: str | None = None,
    source: str = "",
) -> JobFeatures:
    title_norm = normalize_title(title or "")
    desc = description_text or ""
    experience = extract_experience(desc)
    seniority = detect_seniority(title_norm, desc, experience.required_years)
    specialization = detect_specialization(title_norm)
    stack = detect_stack(title_norm, desc)

    return JobFeatures(
        title_raw=title or "",
        title_norm=title_norm,
        description_text=desc,
        seniority=seniority,
        specialization=specialization,
        stack=stack,
        experience=experience,
        remote=remote,
        country=country,
        region=region,
        posted_at=posted_at,
        company_name=company_name,
        source=source,
    )
