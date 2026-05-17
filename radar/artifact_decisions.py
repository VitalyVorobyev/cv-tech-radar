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
from radar.schemas import RadarRing
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
    uncertain: bool = False,
) -> ArtifactDecision:
    """Record a durable radar decision for an artifact.

    Raises :class:`radar.decisions.DecisionError` if the artifact does not
    exist. When ``tracks`` is ``None`` the artifact's own ``tracks_json`` is
    used. ``previous_ring`` is taken from the latest prior decision, and
    ``Artifact.first_decided_at`` is set on the first decision.
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

    decision = ArtifactDecision(
        artifact_id=artifact_id,
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
    if artifact.first_decided_at is None:
        artifact.first_decided_at = decision.created_at
        session.flush()
    return decision


__all__ = ["DecisionError", "record_artifact_decision"]
