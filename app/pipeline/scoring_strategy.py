"""Region-aware scoring strategies.

EGYPT strategy ranks Java backend specialists ABOVE generic SWE.
INTERNATIONAL strategy ranks generic SWE / new-grad pipelines + recognized
top-tier companies + visa-sponsorship signals ABOVE pure Java enterprise.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.db.models import Region


@dataclass(frozen=True)
class Strategy:
    region: Region
    description: str
    multipliers: dict[str, float] = field(default_factory=dict)


EGYPT_STRATEGY = Strategy(
    region=Region.EGYPT,
    description=(
        "Egypt strategy: prioritize Java backend specialists "
        "(Java / Spring / Hibernate / Kafka / microservices) and junior/mid "
        "backend engineers. Generic Software Engineer roles are valued less "
        "unless backend-heavy."
    ),
    multipliers={
        # Java stack: heavily amplified
        "stack_java_title": 1.6,
        "stack_spring_title": 1.6,
        "stack_microservices_title": 1.4,
        "stack_java_desc": 1.4,
        "stack_spring_desc": 1.4,
        "stack_hibernate_jpa": 1.4,
        "stack_kafka": 1.3,
        "stack_java_backend_synergy": 1.6,
        # Backend specialist: amplified
        "spec_backend": 1.4,
        # Generic SWE: dampened
        "spec_generic_swe_engineering_heavy": 0.7,
        "spec_generic_swe": 0.5,
        "spec_generic_swe_thin": 0.3,
        # New-grad pipeline: slightly dampened (less common in Egypt)
        "seniority_graduate": 0.8,
        # Local presence
        "location_egypt": 1.0,
        # Frontend/full-stack: extra penalty in Egypt
        "penalty_frontend_heavy": 1.2,
        "spec_fullstack_neutral": 1.3,
        # Egypt-tier company: small boost
        "company_tier_eg_t1": 1.0,
        # Visa/relocation isn't relevant in Egypt
        "visa_relocation": 0.3,
    },
)


INTERNATIONAL_STRATEGY = Strategy(
    region=Region.INTERNATIONAL,
    description=(
        "International (USA/Europe) strategy: prioritize Junior/New-Grad "
        "Software Engineer roles at globally elite engineering companies "
        "(Tier-S). Strong visa/relocation signals, modern engineering stacks, "
        "and platform/distributed-systems work get major boosts. Pure Java "
        "enterprise roles rank lower."
    ),
    multipliers={
        # Generic SWE: heavily amplified internationally — IF engineering-heavy
        "spec_generic_swe_engineering_heavy": 1.6,
        "spec_generic_swe": 1.2,
        "spec_generic_swe_thin": 0.7,
        # Junior/new-grad: amplified
        "seniority_graduate": 1.4,
        "seniority_junior": 1.2,
        # Backend: solid but secondary
        "spec_backend": 1.1,
        # Java stack: dampened
        "stack_java_title": 0.6,
        "stack_spring_title": 0.6,
        "stack_java_desc": 0.5,
        "stack_spring_desc": 0.5,
        "stack_java_backend_synergy": 0.7,
        # Modern engineering: heavily amplified
        "stack_modern_backend_synergy": 1.4,
        "stack_containerization": 1.3,
        "stack_microservices_desc": 1.3,
        "stack_microservices_title": 1.3,
        # Remote: strong amplifier
        "location_remote": 1.4,
        # Company tier: HUGE amplifier (user-requested)
        "company_tier_s": 1.5,   # Stripe/OpenAI/Google etc. — adds big boost
        "company_tier_a": 1.3,   # Spotify/Booking/Datadog etc.
        "company_tier_b": 1.0,
        # Visa/relocation: heavily amplified for international (user-requested)
        "visa_relocation": 1.6,
        # Modern engineering signals: amplified
        "modern_scale_signals": 1.3,
        "modern_platform_signals": 1.3,
        # Growth signals: amplified (career upside)
        "growth_signals": 1.2,
    },
)


_STRATEGIES = {
    Region.EGYPT: EGYPT_STRATEGY,
    Region.INTERNATIONAL: INTERNATIONAL_STRATEGY,
}


def strategy_for(region: Region) -> Strategy:
    return _STRATEGIES.get(region, INTERNATIONAL_STRATEGY)
