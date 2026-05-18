from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from radar.db import session_scope
from radar.models import (
    Artifact,
    ArtifactDecision,
    ArtifactEvent,
    ArtifactRef,
    ArtifactState,
)


def _seed_artifact(session) -> Artifact:
    artifact = Artifact(
        key="opencv",
        name="OpenCV",
        status="adopted",
        capability="cv-imaging",
        tracks_json=["Open-Source CV Tooling"],
    )
    session.add(artifact)
    session.flush()
    return artifact


def test_artifact_round_trips_with_refs_state_events_decisions(db_engine):
    with session_scope(db_engine) as session:
        artifact = _seed_artifact(session)
        ref = ArtifactRef(artifact_id=artifact.id, ecosystem="github", ref="opencv/opencv")
        session.add(ref)
        session.flush()
        session.add(ArtifactState(artifact_ref_id=ref.id, last_version="4.10.0"))
        session.add(
            ArtifactEvent(
                artifact_id=artifact.id,
                artifact_ref_id=ref.id,
                event_type="release",
                event_date=datetime(2026, 5, 1, tzinfo=UTC),
                version="4.11.0",
                summary="OpenCV 4.11.0 released",
                url="https://github.com/opencv/opencv/releases/tag/4.11.0",
            )
        )
        session.add(
            ArtifactDecision(
                artifact_id=artifact.id, ring="Use", decision_reason="Core dependency."
            )
        )

    with session_scope(db_engine) as session:
        artifact = session.scalar(select(Artifact).where(Artifact.key == "opencv"))
        assert artifact is not None
        assert artifact.capability == "cv-imaging"
        assert len(artifact.refs) == 1
        state = artifact.refs[0].state
        assert state is not None
        assert state.last_version == "4.10.0"
        assert state.last_status == "ok"
        assert [event.version for event in artifact.events] == ["4.11.0"]
        assert artifact.events[0].relevant is False
        assert [decision.ring for decision in artifact.decisions] == ["Use"]


def test_artifact_event_is_idempotent_on_ref_type_version(db_engine):
    with session_scope(db_engine) as session:
        artifact = _seed_artifact(session)
        ref = ArtifactRef(artifact_id=artifact.id, ecosystem="github", ref="opencv/opencv")
        session.add(ref)
        session.flush()
        artifact_id, ref_id = artifact.id, ref.id

    def add_release(session) -> None:
        session.add(
            ArtifactEvent(
                artifact_id=artifact_id,
                artifact_ref_id=ref_id,
                event_type="release",
                event_date=datetime(2026, 5, 1, tzinfo=UTC),
                version="4.11.0",
                url="https://example.test/release",
            )
        )

    with session_scope(db_engine) as session:
        add_release(session)

    with pytest.raises(IntegrityError), session_scope(db_engine) as session:
        add_release(session)


def test_artifact_ref_is_unique_per_ecosystem_ref(db_engine):
    with session_scope(db_engine) as session:
        artifact = _seed_artifact(session)
        session.add(ArtifactRef(artifact_id=artifact.id, ecosystem="github", ref="opencv/opencv"))

    with pytest.raises(IntegrityError), session_scope(db_engine) as session:
        artifact = session.scalar(select(Artifact).where(Artifact.key == "opencv"))
        assert artifact is not None
        session.add(ArtifactRef(artifact_id=artifact.id, ecosystem="github", ref="opencv/opencv"))
