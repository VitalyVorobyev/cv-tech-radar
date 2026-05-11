from __future__ import annotations

from datetime import UTC, datetime

from radar.models import Item, Source
from radar.schemas import AppConfig, RadarRing


def score_source_priority(source: Source | None, config: AppConfig, text: str) -> float:
    score = float((source.priority if source else 0) * 20)
    lower_text = text.casefold()
    for name in config.priority_sources.organizations.get("high", []):
        if name.casefold() in lower_text:
            score += 20
    for name in config.priority_sources.organizations.get("medium", []):
        if name.casefold() in lower_text:
            score += 10
    for name in config.priority_sources.vendors.get("high", []):
        if name.casefold() in lower_text:
            score += 20
    return min(score, float(config.scoring.source_priority_cap))


def score_implementation(item: Item) -> float:
    text = f"{item.title} {item.abstract_or_summary} {item.url} {item.pdf_url or ''}".casefold()
    metadata = item.metadata_json or {}
    comment = str(metadata.get("comment") or "").casefold()
    combined = f"{text} {comment}"
    score = 0.0
    if "github.com" in combined or "code is available" in combined or "source code" in combined:
        score += 45
    if "dataset" in combined or "benchmark" in combined:
        score += 20
    if "real-time" in combined or "real time" in combined or "open-source" in combined:
        score += 15
    return min(score, 100.0)


def score_novelty(item: Item, *, now: datetime | None = None) -> float:
    now = now or datetime.now(UTC)
    published = item.published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    age_days = max((now - published).days, 0)
    if age_days <= 1:
        return 80.0
    if age_days <= 7:
        return 60.0
    if age_days <= 30:
        return 30.0
    return 10.0


def final_score(
    *,
    relevance: float,
    source_priority: float,
    implementation: float,
    attention: float,
    novelty: float,
    negative_penalty: float,
    config: AppConfig,
) -> float:
    weights = config.scoring.weights
    score = (
        relevance * weights.relevance
        + source_priority * weights.source_priority
        + implementation * weights.implementation
        + attention * weights.attention
        + novelty * weights.novelty
        - negative_penalty * weights.negative_penalty
    )
    return round(max(0.0, min(100.0, score)), 2)


def recommended_ring(score: float, config: AppConfig) -> RadarRing:
    thresholds = config.scoring.thresholds
    if score >= thresholds.use:
        return RadarRing.USE
    if score >= thresholds.prototype:
        return RadarRing.PROTOTYPE
    if score >= thresholds.evaluate:
        return RadarRing.EVALUATE
    if score >= thresholds.watch:
        return RadarRing.WATCH
    return RadarRing.IGNORE
