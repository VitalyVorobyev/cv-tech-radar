"""Tests for ``record_artifact_decision`` — the artifact curator-decision API."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from radar.artifact_decisions import DecisionError, record_artifact_decision
from radar.db import session_scope
from radar.models import Artifact, ArtifactDecision
from radar.schemas import RadarRing


def _as_utc(moment: datetime) -> datetime:
    """SQLite drops tzinfo on read; normalise for equality checks."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


def _seed_artifact(db_engine) -> int:
    with session_scope(db_engine) as session:
        artifact = Artifact(
            key="opencv",
            name="OpenCV",
            status="adopted",
            capability="cv-imaging",
            tracks_json=["Open-Source CV Tooling"],
        )
        session.add(artifact)
        session.flush()
        return artifact.id


def test_record_artifact_decision_rejects_unknown_artifact(db_engine):
    with session_scope(db_engine) as session, pytest.raises(DecisionError):
        record_artifact_decision(
            session,
            artifact_id=999,
            ring=RadarRing.IGNORE,
            tracks=[],
            reason="No artifact.",
            action="",
            decided_by="tester",
        )


def test_record_artifact_decision_defaults_to_artifact_tracks(db_engine):
    artifact_id = _seed_artifact(db_engine)
    with session_scope(db_engine) as session:
        decision = record_artifact_decision(
            session,
            artifact_id=artifact_id,
            ring=RadarRing.USE,
            tracks=None,
            reason="Core dependency.",
            action="Keep on Use.",
            decided_by="tester",
        )
        assert decision.tracks_json == ["Open-Source CV Tooling"]


def test_first_decision_sets_first_decided_at_and_null_previous_ring(db_engine):
    artifact_id = _seed_artifact(db_engine)
    with session_scope(db_engine) as session:
        decision = record_artifact_decision(
            session,
            artifact_id=artifact_id,
            ring=RadarRing.WATCH,
            tracks=[],
            reason="first decision",
            action="",
            decided_by="tester",
        )
        decision_created_at = decision.created_at
        assert decision.previous_ring is None

    with session_scope(db_engine) as session:
        artifact = session.get(Artifact, artifact_id)
        assert artifact is not None
        assert artifact.first_decided_at is not None
        assert _as_utc(artifact.first_decided_at) == decision_created_at


def test_second_decision_sets_previous_ring_and_keeps_first_decided_at(db_engine):
    artifact_id = _seed_artifact(db_engine)
    with session_scope(db_engine) as session:
        first = record_artifact_decision(
            session,
            artifact_id=artifact_id,
            ring=RadarRing.WATCH,
            tracks=[],
            reason="first",
            action="",
            decided_by="tester",
        )
        first_ring = first.ring
        first_created = first.created_at

    with session_scope(db_engine) as session:
        second = record_artifact_decision(
            session,
            artifact_id=artifact_id,
            ring=RadarRing.USE,
            tracks=[],
            reason="promote",
            action="",
            decided_by="tester",
        )
        # previous_ring carries the prior decision's ring.
        assert second.previous_ring == first_ring

    with session_scope(db_engine) as session:
        artifact = session.get(Artifact, artifact_id)
        assert artifact is not None
        # first_decided_at must be unchanged after the second decision.
        assert _as_utc(artifact.first_decided_at) == first_created
        decisions = session.scalars(
            select(ArtifactDecision)
            .where(ArtifactDecision.artifact_id == artifact_id)
            .order_by(ArtifactDecision.created_at)
        ).all()
        assert [d.ring for d in decisions] == ["Watch", "Use"]
