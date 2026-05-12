from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.api.deps import get_config, get_session
from radar.api.schemas import (
    CandidateOut,
    CandidateScoresOut,
    CurrentDecisionOut,
    QueueResponse,
)
from radar.models import RadarDecision
from radar.reports.candidate_queue import collect_candidates
from radar.schemas import AppConfig
from radar.utils import parse_date_arg

router = APIRouter(tags=["queue"])


@router.get("/queue", response_model=QueueResponse)
def get_queue(
    session: Annotated[Session, Depends(get_session)],
    config: Annotated[AppConfig, Depends(get_config)],
    date: Annotated[str, Query()] = "today",
    limit: Annotated[int, Query(ge=1, le=500)] = 25,
) -> QueueResponse:
    try:
        target_date = parse_date_arg(date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid date: {exc}") from exc

    effective_limit = min(limit, config.scoring.candidate_limit)
    candidates = collect_candidates(session, target_date, limit=effective_limit)

    out: list[CandidateOut] = []
    for candidate in candidates:
        latest = session.scalar(
            select(RadarDecision)
            .where(RadarDecision.item_id == candidate.id)
            .order_by(RadarDecision.created_at.desc())
            .limit(1)
        )
        current = (
            CurrentDecisionOut(
                id=latest.id,
                ring=latest.ring,
                reason=latest.decision_reason,
                action=latest.action,
                tracks=latest.tracks_json or [],
                uncertain=bool(latest.uncertain),
                decided_by=latest.decided_by,
                created_at=latest.created_at,
            )
            if latest is not None
            else None
        )
        out.append(
            CandidateOut(
                id=candidate.id,
                type=str(candidate.type),
                title=candidate.title,
                abstract=candidate.summary,
                url=candidate.url,
                pdf_url=candidate.pdf_url,
                source=candidate.source,
                published_at=candidate.published_at,
                tracks=candidate.tracks,
                scores=CandidateScoresOut(
                    relevance=candidate.scores.relevance,
                    source_priority=candidate.scores.source_priority,
                    implementation=candidate.scores.implementation,
                    attention=candidate.scores.attention,
                    novelty=candidate.scores.novelty,
                    negative_penalty=candidate.scores.negative_penalty,
                    final=candidate.scores.final,
                ),
                ring_suggested=candidate.ring,
                pipeline_rationale=candidate.pipeline_rationale,
                current_decision=current,
            )
        )

    return QueueResponse(date=target_date.isoformat(), candidates=out)
