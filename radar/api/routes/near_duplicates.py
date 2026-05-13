"""Surface embedding-based near-duplicate pairs in the UI.

This is the visible counterpart to the long-running ``radar embed`` and
``radar near-duplicates`` CLI commands. The route is read-only: it
queries already-stored embeddings, never produces new ones. If the user
hasn't run ``radar embed`` for the requested window, the response is
empty rather than computing on demand (embedding is slow and we don't
want a request stalling for tens of seconds).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from radar.api.deps import get_config, get_session
from radar.embeddings import find_near_duplicates
from radar.schemas import AppConfig
from radar.utils import parse_date_arg

router = APIRouter(tags=["near-duplicates"])


class NearDuplicateOut(BaseModel):
    item_a_id: int
    item_a_title: str
    item_a_external_id: str | None
    item_b_id: int
    item_b_title: str
    item_b_external_id: str | None
    cosine: float


class NearDuplicatesResponse(BaseModel):
    date: str
    days: int
    threshold: float
    model: str
    pairs: list[NearDuplicateOut]


@router.get("/near-duplicates", response_model=NearDuplicatesResponse)
def get_near_duplicates(
    session: Annotated[Session, Depends(get_session)],
    config: Annotated[AppConfig, Depends(get_config)],
    date: Annotated[str, Query()] = "today",
    days: Annotated[int, Query(ge=1, le=365)] = 14,
    threshold: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
) -> NearDuplicatesResponse:
    try:
        target_date = parse_date_arg(date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid date: {exc}") from exc

    settings = config.embeddings.embeddings
    cutoff = threshold if threshold is not None else settings.near_duplicate_threshold
    pairs = find_near_duplicates(
        session,
        target_date,
        days=days,
        threshold=cutoff,
        model=settings.model,
    )
    return NearDuplicatesResponse(
        date=target_date.isoformat(),
        days=days,
        threshold=cutoff,
        model=settings.model,
        pairs=[
            NearDuplicateOut(
                item_a_id=pair.item_a_id,
                item_a_title=pair.item_a_title,
                item_a_external_id=pair.item_a_external_id,
                item_b_id=pair.item_b_id,
                item_b_title=pair.item_b_title,
                item_b_external_id=pair.item_b_external_id,
                cosine=pair.cosine,
            )
            for pair in pairs
        ],
    )
