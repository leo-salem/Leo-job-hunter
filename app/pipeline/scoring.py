"""Public scoring API.

Thin facade over scoring_features + scoring_rules + scoring_strategy.
All scoring goes through score_job(...).
"""
from __future__ import annotations

from app.db.models import Region
from app.pipeline.scoring_features import build_features
from app.pipeline.scoring_rules import ScoreResult, evaluate
from app.pipeline.scoring_strategy import strategy_for


def score_job(
    *,
    title: str,
    description_text: str | None,
    remote: bool,
    country: str | None,
    region: Region,
    posted_at=None,
    company_name: str | None = None,
    source: str = "",
) -> ScoreResult:
    features = build_features(
        title=title,
        description_text=description_text,
        remote=remote,
        country=country,
        region=region,
        posted_at=posted_at,
        company_name=company_name,
        source=source,
    )
    strategy = strategy_for(region)
    return evaluate(features, strategy)


def score_only(**kwargs) -> int:
    return score_job(**kwargs).score
