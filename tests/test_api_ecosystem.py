from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.db import ensure_sources, get_engine, init_db, session_scope
from radar.models import Artifact, ArtifactEvent, ArtifactRef, ArtifactState


@pytest.fixture
def api_db(tmp_path, app_config):
    """A fresh sqlite path; the app factory initializes it."""
    db_path = tmp_path / "api.sqlite"
    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        ensure_sources(session, app_config.sources)
    return db_path, engine


@pytest.fixture
def client(api_db):
    db_path, _engine = api_db
    app = create_app(db_path=db_path, config_dir=Path("config"))
    with TestClient(app) as test_client:
        yield test_client


def _seed_artifact(
    session,
    *,
    key: str,
    name: str,
    status: str,
    capability: str = "cv-imaging",
    tracks: list[str] | None = None,
) -> Artifact:
    artifact = Artifact(
        key=key,
        name=name,
        description=f"{name} description.",
        status=status,
        capability=capability,
        tracks_json=tracks or [],
        homepage_url="",
    )
    session.add(artifact)
    session.flush()
    return artifact


def _seed_ref(
    session, artifact: Artifact, *, ecosystem: str, ref: str, last_version: str | None = None
) -> ArtifactRef:
    ref_row = ArtifactRef(artifact_id=artifact.id, ecosystem=ecosystem, ref=ref)
    session.add(ref_row)
    session.flush()
    if last_version is not None:
        session.add(
            ArtifactState(artifact_ref_id=ref_row.id, last_version=last_version, last_status="ok")
        )
        session.flush()
    return ref_row


def _seed_event(
    session,
    artifact: Artifact,
    ref: ArtifactRef,
    *,
    version: str,
    event_date: datetime,
    relevant: bool,
    severity: str = "medium",
) -> ArtifactEvent:
    event = ArtifactEvent(
        artifact_id=artifact.id,
        artifact_ref_id=ref.id,
        event_type="release",
        event_date=event_date,
        version=version,
        summary=f"{artifact.name} {version}",
        body="release notes",
        url=f"https://example.test/{artifact.key}/{version}",
        severity=severity,
        relevant=relevant,
        matched_keywords_json=[],
    )
    session.add(event)
    session.flush()
    return event


def test_board_seeds_uncurated_artifacts_by_status(client, api_db):
    _db_path, engine = api_db
    with session_scope(engine) as session:
        adopted = _seed_artifact(session, key="opencv-x", name="OpenCV X", status="adopted")
        _seed_ref(session, adopted, ecosystem="github", ref="opencv/opencv")
        _seed_artifact(
            session,
            key="rerun-x",
            name="Rerun X",
            status="watchlist",
            capability="viz-3d-sensors",
        )

    body = client.get("/api/ecosystem/board").json()
    rings = body["rings"]
    # adopted -> seed ring Use; watchlist -> seed ring Watch.
    assert [a["key"] for a in rings["Use"]] == ["opencv-x"]
    assert [a["key"] for a in rings["Watch"]] == ["rerun-x"]
    assert rings["Use"][0]["ecosystems"] == ["github"]
    assert rings["Use"][0]["movement"] is None  # uncurated -> no movement
    assert body["counts"]["Use"] == 1
    assert body["counts"]["Watch"] == 1


def test_board_decision_overrides_seed_ring(client, api_db):
    _db_path, engine = api_db
    with session_scope(engine) as session:
        artifact = _seed_artifact(session, key="opencv-x", name="OpenCV X", status="adopted")
        artifact_id = artifact.id

    post = client.post(
        "/api/ecosystem/decisions",
        json={
            "artifact_id": artifact_id,
            "ring": "Evaluate",
            "reason": "Re-evaluating after a major release.",
        },
    )
    assert post.status_code == 201

    rings = client.get("/api/ecosystem/board").json()["rings"]
    assert rings["Use"] == []
    assert [a["key"] for a in rings["Evaluate"]] == ["opencv-x"]


def test_board_excludes_ignore_by_default(client, api_db):
    _db_path, engine = api_db
    with session_scope(engine) as session:
        artifact = _seed_artifact(session, key="dead-lib", name="Dead Lib", status="watchlist")
        artifact_id = artifact.id

    client.post(
        "/api/ecosystem/decisions",
        json={"artifact_id": artifact_id, "ring": "Ignore", "reason": "Abandoned upstream."},
    )

    default = client.get("/api/ecosystem/board").json()
    assert default["rings"]["Ignore"] == []
    assert default["counts"]["Ignore"] == 1

    with_ignore = client.get("/api/ecosystem/board", params={"include_ignore": "true"}).json()
    assert [a["key"] for a in with_ignore["rings"]["Ignore"]] == ["dead-lib"]


def test_decision_post_unknown_artifact_returns_404(client):
    response = client.post(
        "/api/ecosystem/decisions",
        json={"artifact_id": 9999, "ring": "Watch", "reason": "no such artifact"},
    )
    assert response.status_code == 404


def test_artifact_detail_returns_refs_events_and_decisions(client, api_db):
    _db_path, engine = api_db
    with session_scope(engine) as session:
        artifact = _seed_artifact(
            session,
            key="opencv-x",
            name="OpenCV X",
            status="adopted",
            tracks=["Open-Source CV Tooling"],
        )
        ref = _seed_ref(
            session, artifact, ecosystem="github", ref="opencv/opencv", last_version="4.11.0"
        )
        _seed_event(
            session,
            artifact,
            ref,
            version="4.11.0",
            event_date=datetime(2026, 5, 14, tzinfo=UTC),
            relevant=True,
        )
        artifact_id = artifact.id

    client.post(
        "/api/ecosystem/decisions",
        json={"artifact_id": artifact_id, "ring": "Use", "reason": "Core dependency."},
    )

    body = client.get(f"/api/ecosystem/artifacts/{artifact_id}").json()
    assert body["key"] == "opencv-x"
    assert body["ring"] == "Use"
    assert body["capability"] == "cv-imaging"
    assert len(body["refs"]) == 1
    assert body["refs"][0]["ecosystem"] == "github"
    assert body["refs"][0]["last_version"] == "4.11.0"
    assert [e["version"] for e in body["events"]] == ["4.11.0"]
    assert [d["ring"] for d in body["decisions"]] == ["Use"]


def test_artifact_detail_unknown_id_returns_404(client):
    assert client.get("/api/ecosystem/artifacts/9999").status_code == 404


def test_events_window_and_relevant_filter(client, api_db):
    _db_path, engine = api_db
    with session_scope(engine) as session:
        artifact = _seed_artifact(session, key="opencv-x", name="OpenCV X", status="adopted")
        ref = _seed_ref(session, artifact, ecosystem="github", ref="opencv/opencv")
        # In-window, relevant.
        _seed_event(
            session,
            artifact,
            ref,
            version="4.11.0",
            event_date=datetime(2026, 5, 14, tzinfo=UTC),
            relevant=True,
        )
        # In-window, not relevant.
        _seed_event(
            session,
            artifact,
            ref,
            version="4.10.9",
            event_date=datetime(2026, 5, 13, tzinfo=UTC),
            relevant=False,
        )
        # Out-of-window, relevant.
        _seed_event(
            session,
            artifact,
            ref,
            version="4.9.0",
            event_date=datetime(2026, 4, 1, tzinfo=UTC),
            relevant=True,
        )

    # Default: relevant only, 7-day window ending 2026-05-15.
    default = client.get("/api/ecosystem/events", params={"date": "2026-05-15", "days": 7}).json()
    assert [e["version"] for e in default["events"]] == ["4.11.0"]

    # relevant_only=false surfaces the non-relevant in-window event too, newest first.
    everything = client.get(
        "/api/ecosystem/events",
        params={"date": "2026-05-15", "days": 7, "relevant_only": "false"},
    ).json()
    assert [e["version"] for e in everything["events"]] == ["4.11.0", "4.10.9"]

    # A wide window reaches the older relevant event.
    wide = client.get("/api/ecosystem/events", params={"date": "2026-05-15", "days": 60}).json()
    assert [e["version"] for e in wide["events"]] == ["4.11.0", "4.9.0"]


def test_events_bad_date_returns_422(client):
    assert client.get("/api/ecosystem/events", params={"date": "not-a-date"}).status_code == 422
