"""Curator decisions for ecosystem artifacts.

Mirrors :mod:`radar.decisions` but writes to ``artifact_decisions``. Decisions
are append-only and latest-wins; each records the ``previous_ring`` so the
ecosystem radar can render ring movement just like the papers radar.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.decisions import DecisionError
from radar.models import Artifact, ArtifactDecision
from radar.schemas import DecisionOrigin, RadarRing
from radar.utils import utc_now


def record_artifact_decision(
    session: Session,
    *,
    artifact_id: int,
    ring: RadarRing,
    tracks: list[str] | None,
    reason: str,
    action: str,
    decided_by: str,
    origin: DecisionOrigin,
    uncertain: bool = False,
) -> ArtifactDecision:
    """Record a durable radar decision for an artifact.

    Raises :class:`radar.decisions.DecisionError` if the artifact does not
    exist. When ``tracks`` is ``None`` the artifact's own ``tracks_json`` is
    used. ``previous_ring`` is taken from the latest prior decision.

    ``origin`` gates visibility exactly as it does for papers: only a ``HUMAN``
    decision confirms itself and puts the artifact on the ecosystem radar, and
    only a confirmed decision stamps ``Artifact.first_decided_at``.
    """
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        msg = f"No artifact found with id {artifact_id}"
        raise DecisionError(msg)

    resolved_tracks = tracks
    if resolved_tracks is None:
        resolved_tracks = list(artifact.tracks_json or [])

    prior_ring = session.scalar(
        select(ArtifactDecision.ring)
        .where(ArtifactDecision.artifact_id == artifact_id)
        .order_by(ArtifactDecision.created_at.desc(), ArtifactDecision.id.desc())
        .limit(1)
    )

    created_at = utc_now()
    is_human = origin is DecisionOrigin.HUMAN
    decision = ArtifactDecision(
        artifact_id=artifact_id,
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
    if is_human and artifact.first_decided_at is None:
        artifact.first_decided_at = decision.created_at
        session.flush()
    return decision


def confirm_artifact_decision(
    session: Session,
    *,
    decision_id: int,
    confirmed_by: str,
) -> ArtifactDecision:
    """Ratify a pending artifact proposal. Idempotent."""
    decision = session.get(ArtifactDecision, decision_id)
    if decision is None:
        msg = f"No artifact decision found with id {decision_id}"
        raise DecisionError(msg)
    if decision.confirmed_at is not None:
        return decision

    decision.confirmed_at = utc_now()
    decision.confirmed_by = confirmed_by
    session.flush()

    artifact = session.get(Artifact, decision.artifact_id)
    if artifact is not None and artifact.first_decided_at is None:
        artifact.first_decided_at = decision.confirmed_at
        session.flush()
    return decision


def latest_confirmed_artifact_decision(
    session: Session, artifact_id: int
) -> ArtifactDecision | None:
    """The artifact's latest confirmed decision — the ecosystem radar gate."""
    return session.scalar(
        select(ArtifactDecision)
        .where(
            ArtifactDecision.artifact_id == artifact_id,
            ArtifactDecision.confirmed_at.is_not(None),
        )
        .order_by(ArtifactDecision.created_at.desc(), ArtifactDecision.id.desc())
        .limit(1)
    )


def latest_pending_artifact_decision(session: Session, artifact_id: int) -> ArtifactDecision | None:
    """The artifact's latest decision, when it is still an unratified proposal."""
    latest = session.scalar(
        select(ArtifactDecision)
        .where(ArtifactDecision.artifact_id == artifact_id)
        .order_by(ArtifactDecision.created_at.desc(), ArtifactDecision.id.desc())
        .limit(1)
    )
    if latest is None or latest.confirmed_at is not None:
        return None
    return latest


__all__ = [
    "DecisionError",
    "confirm_artifact_decision",
    "latest_confirmed_artifact_decision",
    "latest_pending_artifact_decision",
    "record_artifact_decision",
]
