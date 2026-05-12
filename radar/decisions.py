from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.models import Item, ItemClassification, RadarDecision
from radar.schemas import RadarRing
from radar.utils import date_bounds, date_window_bounds, utc_now


class DecisionError(RuntimeError):
    pass


def record_decision(
    session: Session,
    *,
    item_id: int,
    ring: RadarRing,
    tracks: list[str] | None,
    reason: str,
    action: str,
    decided_by: str,
    uncertain: bool = False,
) -> RadarDecision:
    item = session.get(Item, item_id)
    if item is None:
        msg = f"No item found with id {item_id}"
        raise DecisionError(msg)

    resolved_tracks = tracks
    if resolved_tracks is None:
        classification = session.scalar(
            select(ItemClassification).where(ItemClassification.item_id == item_id)
        )
        resolved_tracks = classification.tracks_json if classification else []

    prior_ring = session.scalar(
        select(RadarDecision.ring)
        .where(RadarDecision.item_id == item_id)
        .order_by(RadarDecision.created_at.desc(), RadarDecision.id.desc())
        .limit(1)
    )

    decision = RadarDecision(
        item_id=item_id,
        ring=ring.value,
        tracks_json=resolved_tracks,
        decision_reason=reason,
        action=action,
        decided_by=decided_by,
        uncertain=uncertain,
        previous_ring=prior_ring,
        created_at=utc_now(),
    )
    session.add(decision)
    session.flush()
    if item.first_decided_at is None:
        item.first_decided_at = decision.created_at
        session.flush()
    return decision


def list_decisions_in_window(
    session: Session,
    target_date: date,
    days: int,
) -> list[tuple[Item, RadarDecision]]:
    start, end = date_window_bounds(target_date, days)
    return list(
        session.execute(
            select(Item, RadarDecision)
            .join(RadarDecision, RadarDecision.item_id == Item.id)
            .where(Item.published_at >= start, Item.published_at <= end)
            .order_by(RadarDecision.created_at.desc(), Item.title.asc())
        ).all()
    )


def has_prior_decision(session: Session, item_id: int) -> bool:
    return (
        session.scalar(select(RadarDecision.id).where(RadarDecision.item_id == item_id).limit(1))
        is not None
    )


def list_decisions_for_date(
    session: Session,
    target_date: date,
) -> list[tuple[Item, RadarDecision]]:
    start, end = date_bounds(target_date)
    return list(
        session.execute(
            select(Item, RadarDecision)
            .join(RadarDecision, RadarDecision.item_id == Item.id)
            .where(Item.published_at >= start, Item.published_at <= end)
            .order_by(RadarDecision.created_at.desc(), Item.title.asc())
        ).all()
    )


def parse_tracks(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [track.strip() for track in value.split(",") if track.strip()]
