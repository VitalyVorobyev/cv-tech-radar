from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.api.deps import get_session
from radar.api.movement import classify_movement
from radar.api.schemas import HistoryEntryOut, ItemDetailOut, PendingProposalOut
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

    # History is the item's *radar* history, so it is built from confirmed
    # decisions only, collapsing consecutive same-ring entries.
    confirmed = [d for d in decisions if d.confirmed_at is not None]
    history: list[HistoryEntryOut] = []
    last_ring: str | None = None
    for d in confirmed:
        if d.ring != last_ring:
            history.append(
                HistoryEntryOut(
                    ring=d.ring,
                    at=d.created_at,
                    origin=d.origin,
                    confirmed_at=d.confirmed_at,
                )
            )
            last_ring = d.ring

    # An unratified proposal is surfaced separately so the panel can offer a
    # Confirm action without ever implying the item is on the radar.
    newest = decisions[-1] if decisions else None
    pending = (
        PendingProposalOut(
            decision_id=newest.id,
            ring=newest.ring,
            tracks=newest.tracks_json or [],
            reason=newest.decision_reason or "",
            action=newest.action or "",
            uncertain=bool(newest.uncertain),
            decided_by=newest.decided_by or "",
            created_at=newest.created_at,
        )
        if newest is not None and newest.confirmed_at is None
        else None
    )

    latest = confirmed[-1] if confirmed else None
    if latest is None:
        # An item that is not on the radar is still legal: it may never have
        # been decided, or its only decision may be a pending proposal. Return
        # a minimal record with an empty ring — the frontend renders that as
        # the "not on the radar" state and uses `pending_proposal` to offer a
        # Confirm action.
        proposal_tracks = pending.tracks if pending is not None else []
        return ItemDetailOut(
            id=item.id,
            title=item.title,
            abstract=item.abstract_or_summary or "",
            url=item.url,
            ring="",
            track=proposal_tracks[0] if proposal_tracks else "",
            tracks=proposal_tracks,
            reason="",
            uncertain=False,
            source=item.source_name,
            published_at=item.published_at,
            decided_at=item.created_at,
            decided_by=None,
            history=[],
            movement=None,
            pending_proposal=pending,
        )

    tracks = latest.tracks_json or []
    movement = classify_movement(
        current_ring=latest.ring,
        previous_ring=latest.previous_ring,
        decided_at=latest.confirmed_at or latest.created_at,
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
        published_at=item.published_at,
        decided_at=latest.created_at,
        decided_by=latest.decided_by or None,
        history=history,
        movement=movement,
        pending_proposal=pending,
    )
