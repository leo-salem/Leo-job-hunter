"""Modular rule evaluators.

Each `_eval_*` function inspects a `JobFeatures` and appends `RuleResult`
entries to the running list. Rules are categorized and order-independent;
the strategy multipliers from `scoring_strategy.py` are applied per-rule by name.

Weights are calibrated so that hitting 90+ requires MANY aligned signals
(strong title + clean specialization + coherent stack + grad-friendly +
recognized company + visa/relocation + modern-eng signals). Hitting 100 is
deliberately rare.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.pipeline.scoring_company import company_tier
from app.pipeline.scoring_features import (
    FRONTEND_HEAVY,
    JAVA_BACKEND_CORE,
    JobFeatures,
    MODERN_BACKEND_CORE,
    NON_JAVA_BACKEND_LANGS,
    Seniority,
    Specialization,
)
from app.pipeline.scoring_signals import (
    BUZZWORDS,
    ENG_HEAVY_PHRASES,
    GROWTH_PHRASES,
    LEGACY_PHRASES,
    LOW_ENG_PHRASES,
    PLATFORM_PHRASES,
    SCALE_PHRASES,
    SPAM_PHRASES,
    SUPPORT_MAINT_PHRASES,
    VISA_PHRASES,
)
from app.pipeline.scoring_strategy import Strategy


# ===== Result types =====

@dataclass
class RuleResult:
    name: str
    category: str
    base_points: float
    final_points: float
    reason: str

    @property
    def is_positive(self) -> bool:
        return self.final_points > 0

    @property
    def is_negative(self) -> bool:
        return self.final_points < 0


@dataclass
class ScoreResult:
    score: int
    raw_score: float
    confidence: int
    quality_label: str
    region: str
    strategy_name: str
    triggered_rules: list[RuleResult] = field(default_factory=list)

    @property
    def positives(self) -> list[str]:
        return [r.reason for r in self.triggered_rules if r.is_positive]

    @property
    def negatives(self) -> list[str]:
        return [r.reason for r in self.triggered_rules if r.is_negative]

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "raw_score": round(self.raw_score, 2),
            "confidence": self.confidence,
            "quality_label": self.quality_label,
            "region": self.region,
            "strategy": self.strategy_name,
            "triggered_rules": [
                {
                    "name": r.name,
                    "category": r.category,
                    "base_points": r.base_points,
                    "final_points": round(r.final_points, 2),
                    "reason": r.reason,
                }
                for r in self.triggered_rules
            ],
            "positives": self.positives,
            "negatives": self.negatives,
        }


# ===== Internal helpers =====

def _add(out, strategy, *, name, category, points, reason):
    mult = strategy.multipliers.get(name, 1.0)
    final = points * mult
    if final == 0:
        return
    out.append(RuleResult(name=name, category=category, base_points=points, final_points=final, reason=reason))


def _count(pattern, text: str) -> int:
    return len(pattern.findall(text or ""))


# ===== Rules: seniority =====

def _eval_seniority(f: JobFeatures, strategy: Strategy, out: list[RuleResult]) -> None:
    if f.seniority == Seniority.STAFF:
        _add(out, strategy, name="seniority_staff", category="seniority", points=-50, reason="Staff/Principal (too senior)")
    elif f.seniority == Seniority.LEAD:
        _add(out, strategy, name="seniority_lead", category="seniority", points=-45, reason="Lead/Manager/Architect (too senior)")
    elif f.seniority == Seniority.SENIOR:
        _add(out, strategy, name="seniority_senior", category="seniority", points=-40, reason="Senior level (too senior)")
    elif f.seniority == Seniority.MID:
        _add(out, strategy, name="seniority_mid", category="seniority", points=6, reason="Mid-level (acceptable)")
    elif f.seniority == Seniority.JUNIOR:
        _add(out, strategy, name="seniority_junior", category="seniority", points=18, reason="Junior / Associate / Entry-level")
    elif f.seniority == Seniority.GRADUATE:
        _add(out, strategy, name="seniority_graduate", category="seniority", points=20, reason="New Grad / Graduate Program")
    elif f.seniority == Seniority.INTERN:
        _add(out, strategy, name="seniority_intern", category="seniority", points=-30, reason="Internship (not applicable)")


# ===== Rules: specialization (with generic-SWE gate) =====

def _eval_specialization(f: JobFeatures, strategy: Strategy, out: list[RuleResult]) -> None:
    spec = f.specialization
    if spec == Specialization.BACKEND:
        _add(out, strategy, name="spec_backend", category="specialization", points=15, reason="Backend specialization")
    elif spec == Specialization.GENERIC_SWE:
        # Generic SWE is gated: only a strong boost if the JD has real engineering signals
        eng_hits = _count(ENG_HEAVY_PHRASES, f.description_text)
        if eng_hits >= 2:
            _add(out, strategy, name="spec_generic_swe_engineering_heavy", category="specialization",
                 points=15, reason=f"Generic SWE but engineering-heavy ({eng_hits} signals)")
        elif eng_hits == 1:
            _add(out, strategy, name="spec_generic_swe", category="specialization",
                 points=8, reason="Generic SWE with some engineering content")
        else:
            _add(out, strategy, name="spec_generic_swe_thin", category="specialization",
                 points=2, reason="Generic SWE (no strong engineering signals)")
    elif spec == Specialization.FULLSTACK:
        backend_hint = bool(f.stack_keys & {"java", "spring", "kafka", "microservices"})
        if backend_hint:
            _add(out, strategy, name="spec_fullstack_backend_leaning", category="specialization",
                 points=4, reason="Fullstack but backend-leaning")
        else:
            _add(out, strategy, name="spec_fullstack_neutral", category="specialization",
                 points=-12, reason="Fullstack (less backend focus)")
    elif spec == Specialization.FRONTEND:
        _add(out, strategy, name="penalty_frontend_heavy", category="specialization",
             points=-35, reason="Frontend specialization (out of scope)")
    elif spec == Specialization.MOBILE:
        _add(out, strategy, name="penalty_mobile", category="specialization", points=-40, reason="Mobile (out of scope)")
    elif spec == Specialization.ML:
        _add(out, strategy, name="penalty_ml", category="specialization", points=-35, reason="ML/AI (out of scope)")
    elif spec == Specialization.DATA:
        _add(out, strategy, name="penalty_data", category="specialization", points=-35, reason="Data engineering (out of scope)")
    elif spec == Specialization.DEVOPS:
        _add(out, strategy, name="penalty_devops", category="specialization", points=-25, reason="DevOps/SRE (adjacent)")
    elif spec == Specialization.QA:
        _add(out, strategy, name="penalty_qa", category="specialization", points=-35, reason="QA/Testing (out of scope)")
    elif spec == Specialization.SECURITY:
        _add(out, strategy, name="penalty_security", category="specialization", points=-30, reason="Security engineering (out of scope)")
    elif spec == Specialization.EMBEDDED:
        _add(out, strategy, name="penalty_embedded", category="specialization", points=-25, reason="Embedded/Firmware (out of scope)")
    elif spec == Specialization.GAME:
        _add(out, strategy, name="penalty_game", category="specialization", points=-30, reason="Game development (out of scope)")


# ===== Rules: stack =====

def _eval_stack(f: JobFeatures, strategy: Strategy, out: list[RuleResult]) -> None:
    if "java" in f.stack_in_title_keys:
        _add(out, strategy, name="stack_java_title", category="stack", points=14, reason="Java in title")
    if "spring" in f.stack_in_title_keys:
        _add(out, strategy, name="stack_spring_title", category="stack", points=14, reason="Spring in title")
    if "microservices" in f.stack_in_title_keys:
        _add(out, strategy, name="stack_microservices_title", category="stack", points=8, reason="Microservices in title")

    java_mention = f.stack.get("java")
    if java_mention and not java_mention.in_title:
        pts = 9 if java_mention.is_required else 5
        ctx = "required" if java_mention.is_required else "preferred"
        _add(out, strategy, name="stack_java_desc", category="stack", points=pts, reason=f"Java in description ({ctx})")

    spring_mention = f.stack.get("spring")
    if spring_mention and not spring_mention.in_title:
        pts = 9 if spring_mention.is_required else 5
        ctx = "required" if spring_mention.is_required else "preferred"
        _add(out, strategy, name="stack_spring_desc", category="stack", points=pts, reason=f"Spring in description ({ctx})")

    if {"hibernate", "jpa"} & f.stack_keys:
        _add(out, strategy, name="stack_hibernate_jpa", category="stack", points=5, reason="JPA / Hibernate mentioned")
    if "kafka" in f.stack_keys:
        _add(out, strategy, name="stack_kafka", category="stack", points=4, reason="Kafka mentioned")
    if "microservices" in f.stack_keys and "microservices" not in f.stack_in_title_keys:
        _add(out, strategy, name="stack_microservices_desc", category="stack", points=3, reason="Microservices in description")
    if "redis" in f.stack_keys:
        _add(out, strategy, name="stack_redis", category="stack", points=2, reason="Redis mentioned")
    if "postgres" in f.stack_keys or "mysql" in f.stack_keys:
        _add(out, strategy, name="stack_relational_db", category="stack", points=2, reason="Postgres/MySQL mentioned")
    if {"docker", "kubernetes"} & f.stack_keys:
        _add(out, strategy, name="stack_containerization", category="stack", points=3, reason="Docker / Kubernetes mentioned")
    if "rest" in f.stack_keys:
        _add(out, strategy, name="stack_rest_api", category="stack", points=2, reason="REST APIs mentioned")
    if {"jwt", "oauth", "keycloak"} & f.stack_keys:
        _add(out, strategy, name="stack_auth", category="stack", points=2, reason="JWT/OAuth/Keycloak mentioned")

    # Coherent Java backend synergy
    java_core_hits = len(f.stack_keys & JAVA_BACKEND_CORE)
    if java_core_hits >= 3:
        bonus = 5 if java_core_hits == 3 else (8 if java_core_hits == 4 else 11)
        _add(out, strategy, name="stack_java_backend_synergy", category="stack",
             points=bonus, reason=f"Coherent Java backend stack ({java_core_hits}/5)")

    # Modern backend stack synergy
    modern_hits = len(f.stack_keys & MODERN_BACKEND_CORE)
    if modern_hits >= 4:
        bonus = 5 if modern_hits == 4 else (8 if modern_hits == 5 else 10)
        _add(out, strategy, name="stack_modern_backend_synergy", category="stack",
             points=bonus, reason=f"Modern backend stack ({modern_hits} components)")

    # Frontend-heavy without backend balance
    frontend_hits = len(f.stack_keys & FRONTEND_HEAVY)
    backend_balance = len(f.stack_keys & (JAVA_BACKEND_CORE | MODERN_BACKEND_CORE))
    if frontend_hits >= 2 and backend_balance < 2:
        _add(out, strategy, name="penalty_frontend_heavy_stack", category="stack",
             points=-18, reason="Frontend-heavy stack with no backend balance")

    # Backend role but in a non-Java language only
    if f.specialization == Specialization.BACKEND:
        other_lang = f.stack_keys & NON_JAVA_BACKEND_LANGS
        if other_lang and "java" not in f.stack_keys:
            _add(out, strategy, name="penalty_non_java_backend", category="stack",
                 points=-8, reason=f"Backend role in {', '.join(sorted(other_lang))} (no Java)")


# ===== Rules: experience =====

def _eval_experience(f: JobFeatures, strategy: Strategy, out: list[RuleResult]) -> None:
    e = f.experience
    if e.has_grad_friendly_phrase:
        _add(out, strategy, name="exp_grad_friendly", category="experience", points=10, reason="Grad-friendly wording")
    if e.range_max is not None and e.range_max <= 2:
        _add(out, strategy, name="exp_range_0_2", category="experience", points=6, reason=f"Experience range {e.range_min or 0}–{e.range_max} years")
    if e.required_years is not None:
        y = e.required_years
        if y <= 1:
            _add(out, strategy, name="exp_required_low", category="experience", points=6, reason=f"Required: {y}+ years")
        elif y <= 2:
            _add(out, strategy, name="exp_required_two", category="experience", points=2, reason="Required: 2+ years")
        elif y == 3:
            _add(out, strategy, name="exp_required_three", category="experience", points=-8, reason="Required: 3+ years")
        elif y == 4:
            _add(out, strategy, name="exp_required_four", category="experience", points=-14, reason="Required: 4+ years")
        elif y >= 5:
            _add(out, strategy, name="exp_required_high", category="experience", points=-25, reason=f"Required: {y}+ years (out of range)")


# ===== Rules: location =====

def _eval_location(f: JobFeatures, strategy: Strategy, out: list[RuleResult]) -> None:
    if f.remote:
        _add(out, strategy, name="location_remote", category="location", points=7, reason="Remote-friendly")
    c = (f.country or "").lower()
    if f.region.value == "EGYPT":
        if "egypt" in c or any(city in c for city in ("cairo", "giza", "alexandria")):
            _add(out, strategy, name="location_egypt", category="location", points=6, reason="Located in Egypt")
    else:
        if "usa" in c or "united states" in c or c == "us":
            _add(out, strategy, name="location_usa", category="location", points=3, reason="USA location")
        elif "europe" in c or c == "eu" or any(
            eu in c for eu in (
                "germany", "france", "spain", "italy", "ireland", "netherlands",
                "united kingdom", "uk", "poland", "portugal", "sweden", "switzerland",
            )
        ):
            _add(out, strategy, name="location_europe", category="location", points=3, reason="Europe location")


# ===== Rules: company tier =====

def _eval_company(f: JobFeatures, strategy: Strategy, out: list[RuleResult]) -> None:
    tier = company_tier(f.company_name)
    if tier == "s":
        _add(out, strategy, name="company_tier_s", category="company", points=15,
             reason=f"Tier-S iconic company ({f.company_name})")
    elif tier == "a":
        _add(out, strategy, name="company_tier_a", category="company", points=9,
             reason=f"Tier-A strong international company ({f.company_name})")
    elif tier == "b":
        _add(out, strategy, name="company_tier_b", category="company", points=4,
             reason=f"Tier-B recognized company ({f.company_name})")
    elif tier == "eg_t1":
        _add(out, strategy, name="company_tier_eg_t1", category="company", points=7,
             reason=f"Recognized Egypt employer ({f.company_name})")
    elif tier == "spam":
        _add(out, strategy, name="penalty_company_spam", category="company", points=-18,
             reason="Staffing / recruitment-agency posting")
    elif tier == "vague":
        _add(out, strategy, name="penalty_company_vague", category="company", points=-8,
             reason="Vague employer (Confidential / Our Client)")


# ===== Rules: recency =====

def _eval_recency(f: JobFeatures, strategy: Strategy, out: list[RuleResult]) -> None:
    if f.posted_at is None:
        return
    now = datetime.now(timezone.utc)
    posted = f.posted_at
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    age_days = (now - posted).days
    if age_days <= 1:
        _add(out, strategy, name="recency_today", category="recency", points=3, reason="Posted within 24h")
    elif age_days <= 3:
        _add(out, strategy, name="recency_three_days", category="recency", points=2, reason="Posted within 3 days")
    elif age_days <= 7:
        _add(out, strategy, name="recency_week", category="recency", points=1, reason="Posted within a week")
    elif age_days > 60:
        _add(out, strategy, name="recency_stale", category="recency", points=-3, reason=f"Posted {age_days} days ago")


# ===== Rules: visa / relocation =====

def _eval_visa(f: JobFeatures, strategy: Strategy, out: list[RuleResult]) -> None:
    hits = _count(VISA_PHRASES, f.description_text)
    if hits == 0:
        return
    pts = min(hits * 6, 14)  # cap so one JD doesn't dominate
    _add(out, strategy, name="visa_relocation", category="visa",
         points=pts, reason=f"Visa sponsorship / relocation language ({hits} phrase{'s' if hits != 1 else ''})")


# ===== Rules: modern engineering / scale =====

def _eval_modern_eng(f: JobFeatures, strategy: Strategy, out: list[RuleResult]) -> None:
    scale = _count(SCALE_PHRASES, f.description_text)
    platform = _count(PLATFORM_PHRASES, f.description_text)
    if scale >= 1:
        pts = min(scale * 4, 12)
        _add(out, strategy, name="modern_scale_signals", category="modern_eng",
             points=pts, reason=f"Scale/distributed-systems language ({scale} signals)")
    if platform >= 1:
        pts = min(platform * 3, 9)
        _add(out, strategy, name="modern_platform_signals", category="modern_eng",
             points=pts, reason=f"Platform/infrastructure language ({platform} signals)")


# ===== Rules: career growth =====

def _eval_growth(f: JobFeatures, strategy: Strategy, out: list[RuleResult]) -> None:
    hits = _count(GROWTH_PHRASES, f.description_text)
    if hits == 0:
        return
    pts = min(hits * 3, 9)
    _add(out, strategy, name="growth_signals", category="growth",
         points=pts, reason=f"Career-growth language ({hits} phrase{'s' if hits != 1 else ''})")


# ===== Rules: role-intent penalties (support / maintenance / legacy / low-eng) =====

def _eval_role_intent_penalty(f: JobFeatures, strategy: Strategy, out: list[RuleResult]) -> None:
    support = _count(SUPPORT_MAINT_PHRASES, f.description_text + " " + f.title_norm)
    if support >= 1:
        _add(out, strategy, name="penalty_support_role", category="role_intent",
             points=-min(support * 8, 20), reason=f"Support/helpdesk language ({support} signals)")
    legacy = _count(LEGACY_PHRASES, f.description_text)
    if legacy >= 1:
        _add(out, strategy, name="penalty_legacy_stack", category="role_intent",
             points=-min(legacy * 5, 14), reason=f"Legacy maintenance language ({legacy} signals)")
    low_eng = _count(LOW_ENG_PHRASES, f.description_text + " " + f.title_norm)
    if low_eng >= 1:
        _add(out, strategy, name="penalty_low_eng", category="role_intent",
             points=-min(low_eng * 6, 14), reason=f"Low-eng / CMS / low-code ({low_eng} signals)")


# ===== Rules: anti-spam / quality =====

def _eval_quality(f: JobFeatures, strategy: Strategy, out: list[RuleResult]) -> None:
    # Description thinness
    if f.description_chars < 200:
        _add(out, strategy, name="penalty_thin_description", category="quality",
             points=-6, reason="Very short job description (<200 chars)")
    elif f.description_chars > 1500:
        _add(out, strategy, name="quality_substantive_description", category="quality",
             points=2, reason="Detailed job description")

    # Spam phrases
    spam = _count(SPAM_PHRASES, f.description_text)
    if spam >= 1:
        _add(out, strategy, name="penalty_spam_phrasing", category="quality",
             points=-min(spam * 6, 14), reason=f"Spammy phrasing ({spam} phrase{'s' if spam != 1 else ''})")

    # Buzzword stuffing
    buzz = _count(BUZZWORDS, f.description_text)
    if buzz >= 3:
        _add(out, strategy, name="penalty_buzzword_stuffing", category="quality",
             points=-min((buzz - 2) * 3, 9), reason=f"Buzzword-heavy ({buzz} buzzwords)")

    # Keyword stuffing (same skill appearing 6+ times)
    if f.description_text:
        text_lower = f.description_text.lower()
        for skill in ("java", "spring", "developer", "engineer"):
            count = text_lower.count(skill)
            if count >= 8:
                _add(out, strategy, name=f"penalty_keyword_stuffing_{skill}", category="quality",
                     points=-4, reason=f"Keyword '{skill}' repeated {count} times")
                break  # only penalize once even if multiple


# ===== Confidence =====

def _calculate_confidence(f: JobFeatures, triggered: list[RuleResult]) -> int:
    base = 30
    pos_count = sum(1 for r in triggered if r.is_positive)
    neg_count = sum(1 for r in triggered if r.is_negative)

    conf = base + min(35, pos_count * 4) + min(10, neg_count * 2)
    if f.description_chars >= 500:
        conf += 12
    if f.seniority != Seniority.UNKNOWN:
        conf += 6
    if f.specialization != Specialization.UNKNOWN:
        conf += 6

    # Conflict: junior-ish title but high years required
    junior_title = f.seniority in (Seniority.JUNIOR, Seniority.GRADUATE, Seniority.INTERN)
    high_years = f.experience.required_years is not None and f.experience.required_years >= 4
    if junior_title and high_years:
        conf -= 18

    return max(0, min(100, conf))


# ===== Quality label =====

def _quality_label(score: int) -> str:
    """Bucket the final 0–100 score into one of 5 named tiers."""
    if score >= 80:
        return "Excellent Fit"
    if score >= 65:
        return "Strong Fit"
    if score >= 50:
        return "Decent Fit"
    if score >= 35:
        return "Weak Fit"
    return "Poor Fit"


# ===== Public entry point =====

def evaluate(features: JobFeatures, strategy: Strategy) -> ScoreResult:
    triggered: list[RuleResult] = []
    _eval_seniority(features, strategy, triggered)
    _eval_specialization(features, strategy, triggered)
    _eval_stack(features, strategy, triggered)
    _eval_experience(features, strategy, triggered)
    _eval_location(features, strategy, triggered)
    _eval_company(features, strategy, triggered)
    _eval_recency(features, strategy, triggered)
    _eval_visa(features, strategy, triggered)
    _eval_modern_eng(features, strategy, triggered)
    _eval_growth(features, strategy, triggered)
    _eval_role_intent_penalty(features, strategy, triggered)
    _eval_quality(features, strategy, triggered)

    raw = sum(r.final_points for r in triggered)
    score = max(0, min(100, int(round(raw))))
    confidence = _calculate_confidence(features, triggered)

    return ScoreResult(
        score=score,
        raw_score=raw,
        confidence=confidence,
        quality_label=_quality_label(score),
        region=features.region.value,
        strategy_name=strategy.region.value,
        triggered_rules=triggered,
    )
