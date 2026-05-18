"""Query helpers for the ecosystem radar API.

Mirrors :mod:`radar.reports.digest` in style: pure SQLAlchemy read helpers,
no ``AppConfig`` dependency. The board helper resolves each artifact's current
ring — its latest curator decision, or a *seed* ring derived from
``Artifact.status`` so a freshly synced artifact appears on the radar before any
curation. The events helper windows :class:`ArtifactEvent` rows just like the
digest windows :class:`Item` rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from radar.models import (
    Artifact,
    ArtifactDecision,
    ArtifactEvent,
    ArtifactRef,
)
from radar.schemas import RadarRing
from radar.utils import date_window_bounds, utc_now

RECENT_EVENT_WINDOW_DAYS = 14


def seed_ring(status: str) -> str:
    """Return the pre-curation ring for an artifact with the given ``status``.

    ``adopted`` artifacts seed to ``Use`` (already in the user's stack);
    everything else (``watchlist`` and any unexpected value) seeds to ``Watch``.
    """
    return RadarRing.USE.value if status == "adopted" else RadarRing.WATCH.value


@dataclass
class EcosystemBoardRow:
    """One artifact's resolved board state.

    ``ring`` is the latest decision's ring, or :func:`seed_ring` when the
    artifact has not been curated. ``decided_at`` / ``previous_ring`` come from
    that latest decision (``None`` when uncurated).
    """

    artifact: Artifact
    ring: str
    decided_at: datetime | None
    previous_ring: str | None
    ecosystems: list[str]
    latest_event: ArtifactEvent | None
    recent_event_count: int


def collect_ecosystem_board_rows(
    session: Session,
    *,
    include_ignore: bool = False,
) -> list[EcosystemBoardRow]:
    """Return one :class:`EcosystemBoardRow` per enabled artifact.

    - ``ring``: the ring of the latest :class:`ArtifactDecision` (by
      ``created_at`` desc, ``id`` desc tiebreak), else the seed ring.
    - artifacts whose resolved ring is ``Ignore`` are dropped unless
      ``include_ignore`` is True.
    """
    artifacts = list(
        session.scalars(
            select(Artifact).where(Artifact.enabled.is_(True)).order_by(Artifact.name.asc())
        )
    )

    rows: list[EcosystemBoardRow] = []
    recent_threshold = utc_now() - timedelta(days=RECENT_EVENT_WINDOW_DAYS)
    for artifact in artifacts:
        latest = _latest_decision(session, artifact.id)
        if latest is None:
            ring = seed_ring(artifact.status)
            decided_at: datetime | None = None
            previous_ring: str | None = None
        else:
            ring = latest.ring
            decided_at = latest.created_at
            previous_ring = latest.previous_ring

        if ring == RadarRing.IGNORE.value and not include_ignore:
            continue

        rows.append(
            EcosystemBoardRow(
                artifact=artifact,
                ring=ring,
                decided_at=decided_at,
                previous_ring=previous_ring,
                ecosystems=_artifact_ecosystems(session, artifact.id),
                latest_event=_latest_event(session, artifact.id),
                recent_event_count=_recent_event_count(session, artifact.id, recent_threshold),
            )
        )
    return rows


def collect_ecosystem_events(
    session: Session,
    *,
    target_date: date,
    days: int,
    relevant_only: bool = True,
    artifact_key: str | None = None,
    ecosystem: str | None = None,
) -> list[tuple[ArtifactEvent, Artifact, ArtifactRef]]:
    """Return ``(event, artifact, ref)`` rows in the ``days``-wide date window.

    The window ends at ``target_date`` and is ``days`` days wide — identical to
    the digest's :func:`radar.utils.date_window_bounds` logic. Events are
    ordered by ``event_date`` desc (``id`` desc tiebreak). Filters:

    - ``relevant_only``: keep only ``relevant`` events (default True).
    - ``artifact_key`` / ``ecosystem``: optional exact-match narrowing.
    """
    start, end = date_window_bounds(target_date, days)
    stmt = (
        select(ArtifactEvent, Artifact, ArtifactRef)
        .join(Artifact, Artifact.id == ArtifactEvent.artifact_id)
        .join(ArtifactRef, ArtifactRef.id == ArtifactEvent.artifact_ref_id)
        .where(ArtifactEvent.event_date >= start, ArtifactEvent.event_date <= end)
        .order_by(ArtifactEvent.event_date.desc(), ArtifactEvent.id.desc())
    )
    if relevant_only:
        stmt = stmt.where(ArtifactEvent.relevant.is_(True))
    if artifact_key is not None:
        stmt = stmt.where(Artifact.key == artifact_key)
    if ecosystem is not None:
        stmt = stmt.where(ArtifactRef.ecosystem == ecosystem)
    return list(session.execute(stmt).all())


def _latest_decision(session: Session, artifact_id: int) -> ArtifactDecision | None:
    return session.scalar(
        select(ArtifactDecision)
        .where(ArtifactDecision.artifact_id == artifact_id)
        .order_by(ArtifactDecision.created_at.desc(), ArtifactDecision.id.desc())
        .limit(1)
    )


def _artifact_ecosystems(session: Session, artifact_id: int) -> list[str]:
    """Return the distinct, sorted ecosystem names of an artifact's refs."""
    values = session.scalars(
        select(ArtifactRef.ecosystem).where(ArtifactRef.artifact_id == artifact_id).distinct()
    ).all()
    return sorted(values)


def _latest_event(session: Session, artifact_id: int) -> ArtifactEvent | None:
    """Return the most recent :class:`ArtifactEvent` across all of an artifact's refs."""
    return session.scalar(
        select(ArtifactEvent)
        .where(ArtifactEvent.artifact_id == artifact_id)
        .order_by(ArtifactEvent.event_date.desc(), ArtifactEvent.id.desc())
        .limit(1)
    )


def _recent_event_count(session: Session, artifact_id: int, threshold: datetime) -> int:
    """Count ``relevant`` events for an artifact in the recent (14-day) window."""
    return (
        session.scalar(
            select(func.count())
            .select_from(ArtifactEvent)
            .where(
                ArtifactEvent.artifact_id == artifact_id,
                ArtifactEvent.relevant.is_(True),
                ArtifactEvent.event_date >= threshold,
            )
        )
        or 0
    )


__all__ = [
    "EcosystemBoardRow",
    "collect_ecosystem_board_rows",
    "collect_ecosystem_events",
    "seed_ring",
]
