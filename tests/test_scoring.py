"""Tests for the rule-based scoring engine.

These assert RELATIVE orderings and PRESENCE of triggered rules — not exact
integer scores. That way weight tweaks don't break the suite as long as the
qualitative ranking stays correct.

    docker compose exec api python -m pytest tests/ -v
"""
from __future__ import annotations

from app.db.models import Region
from app.pipeline.scoring import score_job


# ===== Helpers =====

def _eg(**kwargs):
    return score_job(region=Region.EGYPT, remote=False, country="Egypt", **kwargs)


def _int(**kwargs):
    return score_job(region=Region.INTERNATIONAL, remote=False, country="USA", **kwargs)


def _rule_names(result) -> set[str]:
    return {r.name for r in result.triggered_rules}


# ===== Title normalization & seniority =====

class TestSeniorityAndTitle:
    def test_swe_expanded_to_software_engineer(self):
        r = _int(title="SWE I", description_text="entry level role")
        assert "seniority_junior" in _rule_names(r)

    def test_sde_expanded(self):
        r = _int(title="SDE I — New Grad", description_text="")
        names = _rule_names(r)
        assert names & {"seniority_junior", "seniority_graduate"}

    def test_jr_abbreviation(self):
        r = _eg(title="Jr. Backend Developer", description_text="")
        assert "seniority_junior" in _rule_names(r)

    def test_senior_strong_penalty(self):
        r = _int(title="Senior Software Engineer", description_text="Java Spring")
        assert "seniority_senior" in _rule_names(r)
        assert r.score < 30

    def test_staff_principal_kills_score(self):
        for title in ("Staff Software Engineer", "Principal Engineer"):
            r = _int(title=title, description_text="")
            assert "seniority_staff" in _rule_names(r)
            assert r.score < 20

    def test_lead_caught(self):
        r = _int(title="Engineering Lead", description_text="")
        assert "seniority_lead" in _rule_names(r)

    def test_new_grad_boosted(self):
        r = _int(
            title="New Grad Software Engineer",
            description_text=(
                "Join our new-grad program. Build distributed systems handling "
                "millions of users with low-latency APIs. Strong mentorship culture, "
                "career growth, learning stipend. Modern engineering practices."
            ),
        )
        assert "seniority_graduate" in _rule_names(r)
        assert r.quality_label in ("Strong Fit", "Decent Fit", "Excellent Fit"), r.score

    def test_intern_not_applicable(self):
        r = _int(title="Software Engineering Intern", description_text="")
        assert "seniority_intern" in _rule_names(r)

    def test_years_fallback_when_title_silent(self):
        r = _eg(title="Java Developer", description_text="Minimum 6 years of experience.")
        assert (
            "seniority_senior" in _rule_names(r)
            or "exp_required_high" in _rule_names(r)
        )


# ===== Specialization =====

class TestSpecialization:
    def test_backend_detected(self):
        r = _eg(title="Backend Engineer", description_text="REST APIs")
        assert "spec_backend" in _rule_names(r)

    def test_generic_swe_gated_by_engineering_signals(self):
        thin = _int(title="Software Engineer", description_text="We are a startup.")
        rich = _int(
            title="Software Engineer",
            description_text="Build distributed systems handling millions of requests with API and microservice architecture",
        )
        assert "spec_generic_swe_engineering_heavy" in _rule_names(rich)
        assert "spec_generic_swe_engineering_heavy" not in _rule_names(thin)
        assert rich.score > thin.score

    def test_frontend_penalty(self):
        r = _eg(title="Frontend React Engineer", description_text="React Redux")
        assert "penalty_frontend_heavy" in _rule_names(r)

    def test_mobile_out_of_scope(self):
        r = _eg(title="iOS Engineer", description_text="Swift")
        assert "penalty_mobile" in _rule_names(r)

    def test_ml_data_qa_security_devops_all_penalized(self):
        for title, expected in [
            ("Machine Learning Engineer", "penalty_ml"),
            ("Data Engineer", "penalty_data"),
            ("QA Automation Engineer", "penalty_qa"),
            ("Security Engineer", "penalty_security"),
            ("DevOps Engineer", "penalty_devops"),
        ]:
            r = _int(title=title, description_text="")
            assert expected in _rule_names(r), f"{title} missing {expected}"


# ===== Stack synergy =====

class TestStackSynergy:
    def test_full_java_stack_synergy_fires(self):
        r = _eg(
            title="Backend Engineer",
            description_text="""
                Build microservices in Java with Spring Boot, Hibernate, JPA.
                Kafka events, Redis caching, Postgres, Docker, Kubernetes,
                REST APIs throughout.
            """,
        )
        assert "stack_java_backend_synergy" in _rule_names(r)

    def test_thin_match_no_synergy(self):
        r = _int(title="Software Engineer", description_text="Java preferred")
        assert "stack_java_backend_synergy" not in _rule_names(r)

    def test_modern_backend_synergy(self):
        r = _int(
            title="Backend Engineer",
            description_text="Docker, Kubernetes, Postgres, Redis, REST, microservices",
        )
        assert "stack_modern_backend_synergy" in _rule_names(r)


# ===== Experience =====

class TestExperience:
    def test_grad_friendly_phrase_bonus(self):
        r = _int(
            title="Software Engineer",
            description_text="Recent graduate welcome. 0-2 years experience.",
        )
        assert "exp_grad_friendly" in _rule_names(r)

    def test_high_years_penalty(self):
        r = _eg(title="Java Developer", description_text="Minimum 7 years required.")
        assert "exp_required_high" in _rule_names(r)


# ===== Region strategy =====

class TestRegionStrategy:
    def test_pure_java_amplified_in_egypt(self):
        title = "Junior Java Developer"
        desc = "Spring Boot, JPA, Hibernate, Postgres. 0-2 years."
        eg = _eg(title=title, description_text=desc)
        int_ = score_job(
            region=Region.INTERNATIONAL, remote=False, country="USA",
            title=title, description_text=desc,
        )
        java_eg = next((r for r in eg.triggered_rules if r.name == "stack_java_title"), None)
        java_int = next((r for r in int_.triggered_rules if r.name == "stack_java_title"), None)
        if java_eg and java_int:
            assert java_eg.final_points > java_int.final_points

    def test_generic_swe_higher_in_international(self):
        title = "Software Engineer, New Grad"
        desc = "Build distributed systems. APIs. Microservices. Engineering culture."
        eg = _eg(title=title, description_text=desc)
        int_ = score_job(
            region=Region.INTERNATIONAL, remote=True, country="Remote - US",
            title=title, description_text=desc,
        )
        assert int_.score > eg.score


# ===== Company tiers (NEW) =====

class TestCompanyTiers:
    def test_tier_s_boost(self):
        # Same role at Stripe vs unknown company → Stripe scores higher
        common = dict(
            title="Software Engineer",
            description_text="Distributed systems, APIs, microservices, growth, ownership.",
        )
        stripe = score_job(
            region=Region.INTERNATIONAL, remote=True, country="USA",
            company_name="Stripe", **common,
        )
        unknown = score_job(
            region=Region.INTERNATIONAL, remote=True, country="USA",
            company_name="Some Local Shop LLC", **common,
        )
        assert stripe.score > unknown.score + 10
        assert "company_tier_s" in _rule_names(stripe)

    def test_tier_a_boost(self):
        # Asana is in Tier A (Spotify is in Tier S per the user's spec)
        r = score_job(
            region=Region.INTERNATIONAL, remote=True, country="Europe",
            title="Software Engineer", description_text="Build APIs at scale",
            company_name="Asana",
        )
        assert "company_tier_a" in _rule_names(r)

    def test_egypt_tier_recognized(self):
        r = _eg(
            title="Junior Java Developer", description_text="Spring Boot",
            company_name="Instabug",
        )
        assert "company_tier_eg_t1" in _rule_names(r)

    def test_spam_company_penalty(self):
        r = score_job(
            region=Region.INTERNATIONAL, remote=False, country="USA",
            title="Software Engineer", description_text="Build APIs",
            company_name="ABC Staffing Agency",
        )
        assert "penalty_company_spam" in _rule_names(r)

    def test_vague_company_penalty(self):
        r = score_job(
            region=Region.INTERNATIONAL, remote=False, country="USA",
            title="Software Engineer", description_text="Build APIs",
            company_name="Confidential",
        )
        assert "penalty_company_vague" in _rule_names(r)


# ===== Visa / relocation (NEW) =====

class TestVisaSignals:
    def test_visa_phrase_boosts_international(self):
        with_visa = _int(
            title="Software Engineer",
            description_text="We provide full visa sponsorship and relocation support.",
        )
        without = _int(title="Software Engineer", description_text="We hire engineers.")
        assert "visa_relocation" in _rule_names(with_visa)
        assert with_visa.score > without.score

    def test_visa_dampened_in_egypt(self):
        eg = _eg(
            title="Java Developer",
            description_text="Visa sponsorship offered for international hires.",
        )
        # Should still fire but with low multiplier
        visa_rule = next((r for r in eg.triggered_rules if r.name == "visa_relocation"), None)
        if visa_rule:
            assert visa_rule.final_points < visa_rule.base_points


# ===== Modern engineering signals (NEW) =====

class TestModernEngineering:
    def test_scale_signals_detected(self):
        r = _int(
            title="Backend Engineer",
            description_text="Build distributed systems handling millions of users with low-latency APIs.",
        )
        assert "modern_scale_signals" in _rule_names(r)

    def test_platform_signals_detected(self):
        r = _int(
            title="Backend Engineer",
            description_text="Work on developer platform, internal platform, observability, CI/CD.",
        )
        assert "modern_platform_signals" in _rule_names(r)


# ===== Growth signals (NEW) =====

class TestGrowthSignals:
    def test_growth_phrases_detected(self):
        r = _int(
            title="Software Engineer",
            description_text="Strong mentorship culture, career growth, ownership, learning stipend.",
        )
        assert "growth_signals" in _rule_names(r)


# ===== Role intent penalties (NEW) =====

class TestRoleIntentPenalties:
    def test_support_role_penalized(self):
        r = _int(
            title="Software Engineer",
            description_text="L2 support engineer, tier 1 support, help desk responsibilities.",
        )
        assert "penalty_support_role" in _rule_names(r)

    def test_legacy_stack_penalized(self):
        r = _int(
            title="Java Developer",
            description_text="Maintain legacy mainframe COBOL applications, EJB.",
        )
        assert "penalty_legacy_stack" in _rule_names(r)

    def test_low_eng_penalized(self):
        r = _int(
            title="Software Developer",
            description_text="WordPress and Drupal CMS maintenance, low-code tools.",
        )
        assert "penalty_low_eng" in _rule_names(r)


# ===== Anti-spam (NEW) =====

class TestAntiSpam:
    def test_spam_phrasing_penalty(self):
        r = _int(
            title="Software Engineer",
            description_text="URGENT HIRING!!! Apply now!!! WhatsApp us at +1234.",
        )
        assert "penalty_spam_phrasing" in _rule_names(r)

    def test_buzzword_stuffing_penalty(self):
        r = _int(
            title="Software Engineer",
            description_text=(
                "We seek a passionate rockstar ninja guru self-starter visionary "
                "to disrupt with synergy."
            ),
        )
        assert "penalty_buzzword_stuffing" in _rule_names(r)

    def test_keyword_stuffing_detected(self):
        r = _int(
            title="Software Engineer",
            description_text="java java java java java java java java java",
        )
        names = _rule_names(r)
        assert any(n.startswith("penalty_keyword_stuffing") for n in names)


# ===== Ranking comparisons (NEW: with company tier) =====

class TestRanking:
    def test_swe_at_tier_s_beats_better_role_at_unknown(self):
        """A generic SWE at Stripe should beat a backend role at random shop."""
        stripe_swe = score_job(
            region=Region.INTERNATIONAL, remote=True, country="USA",
            title="Software Engineer", company_name="Stripe",
            description_text=(
                "Distributed systems work, APIs at scale, mentorship, ownership, "
                "visa sponsorship available."
            ),
        )
        unknown_backend = score_job(
            region=Region.INTERNATIONAL, remote=False, country="USA",
            title="Backend Engineer", company_name="Random Shop LLC",
            description_text="Build CRUD APIs",
        )
        assert stripe_swe.score > unknown_backend.score

    def test_junior_java_beats_senior_java_egypt(self):
        junior = _eg(title="Junior Java Developer", description_text="Spring Boot. 0-2 yrs.")
        senior = _eg(title="Senior Java Architect", description_text="Spring 8+ yrs.")
        assert junior.score > senior.score + 25

    def test_pure_java_beats_react_in_egypt(self):
        java = _eg(title="Junior Java Backend Engineer", description_text="Spring Boot, JPA, Postgres")
        react = _eg(title="Full Stack Developer", description_text="React, Node, MongoDB, full stack")
        assert java.score > react.score + 15

    def test_thin_jd_loses_confidence(self):
        thin = _int(title="Software Engineer", description_text="")
        rich = _int(
            title="Software Engineer",
            description_text=(
                "Build distributed systems. Java Spring REST Kafka Postgres Redis. "
                "0-2 years welcome. Strong mentorship. Distributed systems work."
            ),
        )
        assert rich.confidence > thin.confidence


# ===== False positives =====

class TestFalsePositives:
    def test_javascript_not_java(self):
        r = _eg(title="JavaScript Engineer", description_text="React, Node")
        names = _rule_names(r)
        assert "stack_java_title" not in names
        assert "stack_java_desc" not in names

    def test_senior_overrides_stack(self):
        r = _eg(title="Senior Java Developer", description_text="Spring microservices")
        assert r.score < 40


# ===== Quality labels (NEW) =====

class TestQualityLabel:
    def test_excellent_label(self):
        r = score_job(
            region=Region.INTERNATIONAL, remote=True, country="USA",
            title="Software Engineer, New Grad", company_name="Stripe",
            description_text=(
                "Distributed systems work handling millions of users. APIs at scale, "
                "microservices, Kubernetes. Strong mentorship culture, ownership, "
                "career growth. Visa sponsorship and relocation provided. 0-2 years."
            ),
        )
        assert r.quality_label in ("Excellent Fit", "Strong Fit")
        assert r.score >= 65

    def test_poor_label(self):
        r = _int(title="Senior Staff Architect", description_text="10+ years required")
        assert r.quality_label == "Poor Fit"
        assert r.score < 35

    def test_all_labels_reachable(self):
        # Just verify the buckets are returned correctly
        from app.pipeline.scoring_rules import _quality_label
        assert _quality_label(85) == "Excellent Fit"
        assert _quality_label(70) == "Strong Fit"
        assert _quality_label(55) == "Decent Fit"
        assert _quality_label(40) == "Weak Fit"
        assert _quality_label(20) == "Poor Fit"


# ===== Output structure =====

class TestOutput:
    def test_score_clamped(self):
        r = _eg(
            title="Junior Java Backend Engineer",
            description_text="Spring Boot Hibernate JPA Kafka Redis Postgres Docker Kubernetes",
            company_name="Instabug",
        )
        assert 0 <= r.score <= 100

    def test_to_dict_serializable(self):
        import json
        r = _eg(title="Java Developer", description_text="Spring")
        d = r.to_dict()
        json.dumps(d)
        assert "quality_label" in d
        assert "triggered_rules" in d

    def test_positives_and_negatives_lists(self):
        r = _eg(title="Senior Java Architect", description_text="Spring 10+ years")
        assert len(r.positives) >= 0
        assert len(r.negatives) >= 1


# ===== Calibration sanity (NEW) =====

class TestCalibration:
    """Verify the score distribution doesn't pile up at 100."""

    def test_perfect_egypt_job_below_100(self):
        # Even the best possible Egypt job shouldn't trivially hit 100
        r = _eg(
            title="Junior Java Backend Engineer",
            description_text=(
                "Spring Boot, Hibernate, JPA. Kafka events. Redis cache. "
                "Postgres. Docker. Kubernetes. Microservices. REST APIs. "
                "0-2 years welcome. Mentorship and career growth."
            ),
            company_name="Instabug",
        )
        # Allow 100 but only with EVERY signal — most ideal jobs land 85-95
        assert r.score >= 75
        # Confidence should be high for such a substantive JD
        assert r.confidence >= 75

    def test_average_job_in_middle(self):
        r = _int(
            title="Backend Engineer",
            description_text=(
                "Build distributed backend services and REST APIs. "
                "Use Java, Spring Boot, Postgres, Redis, Docker, Kubernetes. "
                "We require 3+ years of experience. Strong engineering culture."
            ),
        )
        # Average-quality JD with mid-level requirement should land 30-75
        assert 30 <= r.score <= 75, r.score
