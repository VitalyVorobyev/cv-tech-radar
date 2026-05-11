from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from radar.api.deps import get_session
from radar.api.schemas import (
    DecisionCreate,
    DecisionCreatedOut,
    DecisionItemRef,
    DecisionListResponse,
    DecisionOut,
)
from radar.decisions import DecisionError, list_decisions_in_window, record_decision
from radar.utils import parse_date_arg

router = APIRouter(tags=["decisions"])


@router.post(
    "/decisions",
    response_model=DecisionCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
def create_decision(
    payload: DecisionCreate,
    session: Annotated[Session, Depends(get_session)],
) -> DecisionCreatedOut:
    try:
        decision = record_decision(
            session,
            item_id=payload.item_id,
            ring=payload.ring,
            tracks=payload.tracks,
            reason=payload.reason,
            action=payload.action,
            decided_by=payload.decided_by,
            uncertain=payload.uncertain,
        )
    except DecisionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    session.flush()
    return DecisionCreatedOut(decision_id=decision.id, created_at=decision.created_at)


@router.get("/decisions", response_model=DecisionListResponse)
def list_decisions(
    session: Annotated[Session, Depends(get_session)],
    date: Annotated[str, Query()] = "today",
    days: Annotated[int, Query(ge=1)] = 1,
) -> DecisionListResponse:
    try:
        target_date = parse_date_arg(date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid date: {exc}") from exc

    rows = list_decisions_in_window(session, target_date, days)
    out = [
        DecisionOut(
            item_id=item.id,
            item=DecisionItemRef(id=item.id, title=item.title, url=item.url),
            ring=decision.ring,
            tracks=decision.tracks_json or [],
            reason=decision.decision_reason,
            action=decision.action,
            uncertain=bool(decision.uncertain),
            decided_by=decision.decided_by,
            created_at=decision.created_at,
        )
        for item, decision in rows
    ]
    return DecisionListResponse(rows=out)
