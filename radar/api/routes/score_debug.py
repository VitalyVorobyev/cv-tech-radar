"""Inspect per-component classification scores for a given date."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from radar.api.deps import get_session
from radar.reports.score_debug import collect_score_debug_rows
from radar.utils import parse_date_arg

router = APIRouter(tags=["score-debug"])


@router.get("/score-debug")
def get_score_debug(
    session: Annotated[Session, Depends(get_session)],
    date: Annotated[str, Query()] = "today",
    limit: Annotated[int, Query(ge=1, le=500)] = 25,
    include_zero: Annotated[bool, Query()] = False,
) -> dict:
    try:
        target_date = parse_date_arg(date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid date: {exc}") from exc

    rows = collect_score_debug_rows(
        session,
        target_date,
        limit=limit,
        include_zero=include_zero,
    )
    items: list[dict] = []
    for item, classification in rows:
        items.append(
            {
                "item_id": item.id,
                "title": item.title,
                "ring": classification.recommended_ring,
                "final": classification.final_score,
                "relevance": classification.relevance_score,
                "source_priority": classification.source_priority_score,
                "implementation": classification.implementation_score,
                "novelty": classification.novelty_score,
                "negative_penalty": classification.negative_topic_penalty,
                "tracks": classification.tracks_json or [],
                "matched_keywords": classification.positive_keywords_json or [],
            }
        )
    return {"date": target_date.isoformat(), "items": items}
