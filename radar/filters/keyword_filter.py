from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.models import Item, ItemClassification, Source
from radar.schemas import AppConfig, ClassificationResult
from radar.scoring.score_item import (
    final_score,
    recommended_ring,
    score_implementation,
    score_novelty,
    score_source_priority,
)
from radar.utils import date_bounds, utc_now


def classify_items_for_date(session: Session, config: AppConfig, target_date) -> int:
    start, end = date_bounds(target_date)
    items = session.scalars(
        select(Item).where(Item.published_at >= start, Item.published_at <= end)
    ).all()
    for item in items:
        source = session.scalar(select(Source).where(Source.name == item.source_name))
        result = classify_item(item, config=config, source=source)
        upsert_classification(session, item, result)
    return len(items)


def classify_item(
    item: Item,
    *,
    config: AppConfig,
    source: Source | None = None,
) -> ClassificationResult:
    title_text = item.title.casefold()
    body_text = item.abstract_or_summary.casefold()
    full_text = f"{title_text} {body_text}"

    selected_tracks: list[str] = []
    positive_keywords: list[str] = []
    track_scores: list[float] = []

    for track in config.topics.tracks:
        score = 0.0
        matches: list[str] = []
        for keyword in track.positive_keywords:
            keyword_lower = keyword.casefold()
            if keyword_lower in title_text:
                score += 18
                matches.append(keyword)
            elif keyword_lower in body_text:
                score += 10
                matches.append(keyword)
        for keyword in track.negative_keywords:
            if keyword.casefold() in full_text:
                score -= 12
        if score > 0:
            selected_tracks.append(track.name)
            positive_keywords.extend(matches)
            track_scores.append(min(score, 100.0))

    negative_keywords = [
        topic for topic in config.negative_topics.negative_topics if topic.casefold() in full_text
    ]
    negative_penalty = min(100.0, 25.0 + max(len(negative_keywords) - 1, 0) * 10.0)
    if not negative_keywords:
        negative_penalty = 0.0

    if track_scores:
        strongest = max(track_scores)
        rest = sum(track_scores) - strongest
        relevance = min(100.0, strongest + rest * 0.6)
    else:
        relevance = 0.0

    source_priority = score_source_priority(source, config, full_text)
    implementation = score_implementation(item)
    attention = 0.0
    novelty = score_novelty(item)
    final = final_score(
        relevance=relevance,
        source_priority=source_priority,
        implementation=implementation,
        attention=attention,
        novelty=novelty,
        negative_penalty=negative_penalty,
        config=config,
    )
    ring = recommended_ring(final, config)
    confidence = min(0.95, 0.3 + len(set(positive_keywords)) * 0.08)

    rationale_parts = []
    if selected_tracks:
        rationale_parts.append(f"Matched tracks: {', '.join(selected_tracks)}.")
    if positive_keywords:
        rationale_parts.append(f"Positive keywords: {', '.join(sorted(set(positive_keywords)))}.")
    if negative_keywords:
        rationale_parts.append(f"Negative topics: {', '.join(negative_keywords)}.")
    if not rationale_parts:
        rationale_parts.append("No configured radar track keywords matched.")

    return ClassificationResult(
        tracks=selected_tracks,
        positive_keywords=sorted(set(positive_keywords)),
        negative_keywords=negative_keywords,
        relevance_score=round(relevance, 2),
        novelty_score=round(novelty, 2),
        source_priority_score=round(source_priority, 2),
        implementation_score=round(implementation, 2),
        attention_score=round(attention, 2),
        final_score=final,
        negative_topic_penalty=round(negative_penalty, 2),
        recommended_ring=ring,
        confidence=round(confidence, 2),
        rationale=" ".join(rationale_parts),
    )


def upsert_classification(session: Session, item: Item, result: ClassificationResult) -> None:
    classification = session.scalar(
        select(ItemClassification).where(ItemClassification.item_id == item.id)
    )
    if classification is None:
        classification = ItemClassification(item_id=item.id)
        session.add(classification)
    classification.tracks_json = result.tracks
    classification.positive_keywords_json = result.positive_keywords
    classification.negative_keywords_json = result.negative_keywords
    classification.relevance_score = result.relevance_score
    classification.novelty_score = result.novelty_score
    classification.source_priority_score = result.source_priority_score
    classification.implementation_score = result.implementation_score
    classification.attention_score = result.attention_score
    classification.negative_topic_penalty = result.negative_topic_penalty
    classification.final_score = result.final_score
    classification.recommended_ring = result.recommended_ring.value
    classification.confidence = result.confidence
    classification.rationale = result.rationale
    classification.created_at = utc_now()
