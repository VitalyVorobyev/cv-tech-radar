from __future__ import annotations

from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from radar.models import Item, ItemClassification, RadarDecision
from radar.schemas import DecisionOrigin, RadarRing
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
    origin: DecisionOrigin,
    uncertain: bool = False,
) -> RadarDecision:
    """Append a decision row for an item.

    ``origin`` is required on purpose: it decides whether the row reaches the
    radar. A ``HUMAN`` decision confirms itself — a person made the call. An
    ``AGENT`` decision is a proposal that stays invisible until someone runs it
    through :func:`confirm_decision`.
    """
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

    created_at = utc_now()
    is_human = origin is DecisionOrigin.HUMAN
    decision = RadarDecision(
        item_id=item_id,
        ring=ring.value,
        tracks_json=resolved_tracks,
        decision_reason=reason,
        action=action,
        decided_by=decided_by,
        origin=origin.value,
        confirmed_at=created_at if is_human else None,
        confirmed_by=decided_by if is_human else None,
        uncertain=uncertain,
        previous_ring=prior_ring,
        created_at=created_at,
    )
    session.add(decision)
    session.flush()
    # first_decided_at tracks the first *confirmed* decision; a proposal does
    # not put the item on the radar, so it must not stamp it.
    if is_human and item.first_decided_at is None:
        item.first_decided_at = decision.created_at
        session.flush()
    return decision


def confirm_decision(
    session: Session,
    *,
    decision_id: int,
    confirmed_by: str,
) -> RadarDecision:
    """Ratify a pending proposal so it reaches the radar. Idempotent."""
    decision = session.get(RadarDecision, decision_id)
    if decision is None:
        msg = f"No decision found with id {decision_id}"
        raise DecisionError(msg)
    if decision.confirmed_at is not None:
        return decision

    decision.confirmed_at = utc_now()
    decision.confirmed_by = confirmed_by
    session.flush()

    item = session.get(Item, decision.item_id)
    if item is not None and item.first_decided_at is None:
        item.first_decided_at = decision.confirmed_at
        session.flush()
    return decision


def latest_confirmed_decision_subq() -> Select[tuple[int]]:
    """Subquery of decision ids: the latest *confirmed* decision per item.

    This is THE radar gate. Every surface that renders radar state — board,
    board counts, digest, timeline, static bundle, item detail — must join
    through this rather than querying ``radar_decisions`` directly, or
    unreviewed agent proposals leak onto the radar.

    Two levels because ``created_at`` ties are real on SQLite's sub-second
    clock: pick max(created_at) per item, then max(id) among the tied rows.
    This matches the tiebreak every existing read site uses.
    """
    latest_created = (
        select(
            RadarDecision.item_id,
            func.max(RadarDecision.created_at).label("max_created"),
        )
        .where(RadarDecision.confirmed_at.is_not(None))
        .group_by(RadarDecision.item_id)
        .subquery()
    )
    return (
        select(func.max(RadarDecision.id).label("decision_id"))
        .join(
            latest_created,
            (RadarDecision.item_id == latest_created.c.item_id)
            & (RadarDecision.created_at == latest_created.c.max_created),
        )
        .where(RadarDecision.confirmed_at.is_not(None))
        .group_by(RadarDecision.item_id)
    )


def latest_pending_decision_subq() -> Select[tuple[int]]:
    """Subquery of decision ids: each item's latest decision, when unconfirmed.

    The inverse of :func:`latest_confirmed_decision_subq` — this is the review
    inbox. An item appears iff its most recent decision of any kind is still an
    unratified proposal, so confirming or overriding one removes it from the
    inbox without any extra bookkeeping.
    """
    latest_created = (
        select(
            RadarDecision.item_id,
            func.max(RadarDecision.created_at).label("max_created"),
        )
        .group_by(RadarDecision.item_id)
        .subquery()
    )
    latest_ids = (
        select(func.max(RadarDecision.id).label("decision_id"))
        .join(
            latest_created,
            (RadarDecision.item_id == latest_created.c.item_id)
            & (RadarDecision.created_at == latest_created.c.max_created),
        )
        .group_by(RadarDecision.item_id)
        .subquery()
    )
    return (
        select(RadarDecision.id)
        .join(latest_ids, RadarDecision.id == latest_ids.c.decision_id)
        .where(RadarDecision.confirmed_at.is_(None))
    )


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
