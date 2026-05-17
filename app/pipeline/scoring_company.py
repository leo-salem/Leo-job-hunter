"""Company-quality tiers.

Four tiers + spam + vague + unknown:

  S — globally iconic engineering/product companies (Stripe, OpenAI, Google, etc.)
       Highest visa-sponsorship probability, strongest compensation/growth.
  A — strong international tech companies (Spotify, Booking, Datadog, etc.)
       Solid engineering culture, decent sponsorship probability.
  B — recognized but lower-priority (most B2B SaaS, regional tech)
  EG_T1 — recognized Egypt employers (used inside EGYPT region only)
  SPAM — recruiters / staffing / outsourcing wrappers
  VAGUE — "leading company" / "confidential" / "our client"
  UNKNOWN — no signal

The S/A/B/EG_T1 names are stable keys downstream rules use to look up weights.
"""
from __future__ import annotations

import re


# Tier S — globally iconic. Strong amplification internationally.
TIER_S = {
    # AI labs
    "openai", "anthropic", "deepmind", "scale ai", "huggingface", "cohere", "mistral",
    "perplexity", "character.ai", "x.ai", "xai",
    # FAANG-class
    "google", "alphabet", "meta", "facebook", "instagram", "whatsapp",
    "apple", "amazon", "amazon web services", "aws",
    "microsoft", "github",
    "netflix", "nvidia",
    # Top-tier product / fintech
    "stripe", "datadog", "cloudflare", "snowflake", "databricks", "palantir",
    "figma", "linear", "notion", "canva", "atlassian",
    "spotify", "shopify", "uber", "airbnb", "lyft", "doordash", "instacart",
    "discord", "reddit",
    "coinbase", "ramp", "brex", "mercury", "wise", "revolut", "robinhood",
    "booking.com", "booking holdings", "adyen", "klarna",
    # High-end quant / fintech engineering
    "jane street", "citadel", "two sigma", "hudson river trading", "drw", "jump trading",
}

# Tier A — strong international engineering culture, good growth, sometimes sponsorship.
TIER_A = {
    "asana", "slack", "zoom", "twilio", "intercom", "miro", "loom",
    "gitlab", "hashicorp", "elastic", "mongodb", "confluent",
    "vercel", "supabase", "render", "fly.io", "planetscale", "neon",
    "pinterest", "snap", "twitch", "duolingo", "khan academy", "patreon",
    "amd", "oracle", "salesforce", "ibm", "intel", "broadcom", "sap",
    "epic games", "roblox", "unity",
    "jpmorgan", "goldman sachs", "morgan stanley", "blackrock",
    "block", "square", "kraken",
    "thoughtworks", "redhat", "red hat", "vmware",
    "indeed", "glassdoor", "expedia", "trivago", "agoda",
    "n26", "monzo", "starling", "trade republic", "scalable capital",
    "delivery hero", "just eat", "deliveroo", "hellofresh", "zalando",
}

# Tier B — recognized but not amplified beyond a small bonus.
TIER_B = {
    "elastic", "couchbase", "redis", "cockroachlabs", "cockroach labs",
    "auth0", "okta", "segment", "datadog", "newrelic", "new relic",
    "sendgrid", "twilio", "mailchimp", "zendesk",
    "freshworks", "monday", "smartsheet",
}

# Egypt / MENA tier 1 employers.
TIER_EG_T1 = {
    "instabug", "swvl", "halan", "valu", "nclude", "trella", "kazyon",
    "fawry", "telda", "khazna", "paymob", "money fellows", "money loop",
    "rasan", "raya holding", "raya", "incorta", "elmenus", "cartona",
    "homzmart", "mountainview", "robusta", "robusta studio",
    "vodafone egypt", "etisalat misr", "orange egypt", "telecom egypt",
    "we egypt", "iti", "bosta", "thndr", "khareta", "tanmeyah", "bankly",
    "agoda egypt", "ibm egypt", "oracle egypt",
    "ejada", "siemens egypt", "valeo egypt",
    "kemitt", "elves", "yallakora", "shahry", "lendable", "lucky",
    "vezeeta", "yalla foundry", "trayd", "axle", "axle health",
    "convertedin", "trella", "mylerz", "shopcash", "deepecho",
}

# Spam / staffing / outsourcing patterns.
_SPAM_PATTERNS = re.compile(
    r"\b(staffing|recruitment\s+agency|outsourcing|consulting\s+(firm|group)|"
    r"talent\s+acquisition\s+(firm|partner|consultancy)|head\s+hunter|"
    r"freelance\s+platform|gig\s+platform)\b",
    re.IGNORECASE,
)

_VAGUE_PATTERNS = re.compile(
    r"\b(confidential|undisclosed|client\s+of\s+ours|our\s+client|"
    r"leading\s+(company|firm|provider|enterprise)|top\s+(company|firm))\b",
    re.IGNORECASE,
)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9\. ]", "", name.strip().lower())


def company_tier(company_name: str | None) -> str:
    """Returns one of: 's', 'a', 'b', 'eg_t1', 'spam', 'vague', 'unknown'."""
    if not company_name:
        return "unknown"
    name = _norm(company_name)
    # Exact match first, then substring containment (e.g. "Stripe, Inc." → "stripe")
    if name in TIER_S or any(t == name or t in name for t in TIER_S):
        return "s"
    if name in TIER_A or any(t == name or t in name for t in TIER_A):
        return "a"
    if name in TIER_EG_T1 or any(t == name or t in name for t in TIER_EG_T1):
        return "eg_t1"
    if name in TIER_B or any(t == name or t in name for t in TIER_B):
        return "b"
    if _SPAM_PATTERNS.search(name):
        return "spam"
    if _VAGUE_PATTERNS.search(name):
        return "vague"
    return "unknown"
