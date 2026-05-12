from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.api.deps import get_session
from radar.api.movement import classify_movement
from radar.api.schemas import HistoryEntryOut, ItemDetailOut
from radar.models import Item, RadarDecision
from radar.utils import utc_now

router = APIRouter(tags=["items"])


@router.get("/items/{item_id}", response_model=ItemDetailOut)
def get_item(
    session: Annotated[Session, Depends(get_session)],
    item_id: Annotated[int, Path(ge=1)],
) -> ItemDetailOut:
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"item {item_id} not found")

    decisions = list(
        session.scalars(
            select(RadarDecision)
            .where(RadarDecision.item_id == item_id)
            .order_by(RadarDecision.created_at.asc(), RadarDecision.id.asc())
        )
    )

    # Build history by collapsing consecutive same-ring entries.
    history: list[HistoryEntryOut] = []
    last_ring: str | None = None
    for d in decisions:
        if d.ring != last_ring:
            history.append(HistoryEntryOut(ring=d.ring, at=d.created_at))
            last_ring = d.ring

    latest = decisions[-1] if decisions else None
    if latest is None:
        # An item with no decision is still legal; return a minimal record so the panel
        # can render. The frontend treats this as the "not yet curated" state.
        return ItemDetailOut(
            id=item.id,
            title=item.title,
            abstract=item.abstract_or_summary or "",
            url=item.url,
            ring="",
            track="",
            tracks=[],
            reason="",
            uncertain=False,
            source=item.source_name,
            decided_at=item.created_at,
            decided_by=None,
            history=[],
            movement=None,
        )

    tracks = latest.tracks_json or []
    movement = classify_movement(
        current_ring=latest.ring,
        previous_ring=latest.previous_ring,
        decided_at=latest.created_at,
        first_decided_at=item.first_decided_at,
        now=utc_now(),
    )

    return ItemDetailOut(
        id=item.id,
        title=item.title,
        abstract=item.abstract_or_summary or "",
        url=item.url,
        ring=latest.ring,
        track=tracks[0] if tracks else "",
        tracks=tracks,
        reason=latest.decision_reason or "",
        uncertain=bool(latest.uncertain),
        source=item.source_name,
        decided_at=latest.created_at,
        decided_by=latest.decided_by or None,
        history=history,
        movement=movement,
    )
