from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.db import session_scope
from radar.filters.keyword_filter import classify_items_for_date
from radar.models import Item, RadarDecision
from radar.schemas import RadarRing


@pytest.fixture
def api_db(tmp_path, app_config):
    """Provide a fresh sqlite path; the app factory will initialize it."""
    from radar.db import ensure_sources, get_engine, init_db

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


def _seed_item(session, *, item_id: int, title: str, published: datetime) -> None:
    session.add(
        Item(
            id=item_id,
            type="paper",
            title=title,
            normalized_title=title.casefold(),
            abstract_or_summary="Camera calibration with bundle adjustment for industrial cameras.",
            url=f"https://example.test/{item_id}",
            pdf_url=f"https://example.test/{item_id}.pdf",
            published_at=published,
            updated_at=None,
            source_name="arXiv cs.CV",
            external_id=f"ext-{item_id}",
            arxiv_id=f"ext-{item_id}",
            authors_json=[],
            organizations_json=[],
            metadata_json={},
        )
    )


def _seed_decision(
    session,
    *,
    item_id: int,
    ring: RadarRing,
    tracks: list[str],
    reason: str,
    created_at: datetime,
    uncertain: bool = False,
) -> None:
    session.add(
        RadarDecision(
            item_id=item_id,
            ring=ring.value,
            tracks_json=tracks,
            decision_reason=reason,
            action="",
            decided_by="tester",
            uncertain=uncertain,
            created_at=created_at,
        )
    )


def test_health_returns_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert isinstance(body["version"], str)


def test_queue_empty_returns_200(client):
    response = client.get("/api/queue", params={"date": "2026-05-11"})
    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-05-11"
    assert body["candidates"] == []


def test_queue_with_seeded_items_has_correct_shape(client, api_db, app_config):
    _db_path, engine = api_db
    target = date(2026, 5, 11)
    published = datetime(2026, 5, 11, 10, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(
            session, item_id=1, title="Subpixel checkerboard calibration", published=published
        )
        session.flush()
        classify_items_for_date(session, app_config, target)

    response = client.get("/api/queue", params={"date": "2026-05-11", "limit": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-05-11"
    assert len(body["candidates"]) == 1
    candidate = body["candidates"][0]
    assert candidate["id"] == 1
    assert candidate["title"] == "Subpixel checkerboard calibration"
    assert candidate["abstract"].startswith("Camera calibration")
    assert candidate["url"] == "https://example.test/1"
    assert candidate["pdf_url"] == "https://example.test/1.pdf"
    assert candidate["source"] == "arXiv cs.CV"
    assert candidate["ring_suggested"] in {"Use", "Prototype", "Evaluate", "Watch", "Ignore"}
    assert candidate["current_decision"] is None
    for key in (
        "relevance",
        "source_priority",
        "implementation",
        "attention",
        "novelty",
        "negative_penalty",
        "final",
    ):
        assert key in candidate["scores"]


def test_queue_shows_current_decision_after_post(client, api_db, app_config):
    _db_path, engine = api_db
    target = date(2026, 5, 11)
    published = datetime(2026, 5, 11, 10, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(
            session, item_id=1, title="Subpixel checkerboard calibration", published=published
        )
        session.flush()
        classify_items_for_date(session, app_config, target)

    post = client.post(
        "/api/decisions",
        json={
            "item_id": 1,
            "ring": "Watch",
            "reason": "Looks promising but light on evaluation.",
            "tracks": ["Calibration & Camera Models"],
            "decided_by": "tester",
        },
    )
    assert post.status_code == 201

    response = client.get("/api/queue", params={"date": "2026-05-11"})
    assert response.status_code == 200
    candidate = response.json()["candidates"][0]
    assert candidate["current_decision"] is not None
    assert candidate["current_decision"]["ring"] == "Watch"
    assert candidate["current_decision"]["decided_by"] == "tester"


def test_decisions_post_happy_path(client, api_db):
    _db_path, engine = api_db
    published = datetime(2026, 5, 11, 10, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(session, item_id=42, title="Hand-eye calibration", published=published)

    response = client.post(
        "/api/decisions",
        json={
            "item_id": 42,
            "ring": "Prototype",
            "reason": "There is a clear test path.",
            "action": "Build a 1-day prototype.",
            "tracks": ["Robotics Vision"],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["decision_id"], int)
    assert body["created_at"]

    # The decision is visible through the list endpoint.
    listed = client.get("/api/decisions", params={"date": "2026-05-11"})
    assert listed.status_code == 200
    rows = listed.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["item_id"] == 42
    assert rows[0]["ring"] == "Prototype"


def test_decisions_post_unknown_item_returns_404(client):
    response = client.post(
        "/api/decisions",
        json={
            "item_id": 9999,
            "ring": "Watch",
            "reason": "No such item.",
        },
    )
    assert response.status_code == 404


def test_decisions_post_bad_ring_returns_422(client, api_db):
    _db_path, engine = api_db
    with session_scope(engine) as session:
        _seed_item(
            session,
            item_id=1,
            title="x",
            published=datetime(2026, 5, 11, 10, tzinfo=UTC),
        )

    response = client.post(
        "/api/decisions",
        json={"item_id": 1, "ring": "NotARing", "reason": "bad"},
    )
    assert response.status_code == 422


def test_decisions_get_window(client, api_db):
    _db_path, engine = api_db
    with session_scope(engine) as session:
        _seed_item(
            session,
            item_id=1,
            title="Today",
            published=datetime(2026, 5, 11, 10, tzinfo=UTC),
        )
        _seed_item(
            session,
            item_id=2,
            title="Two days ago",
            published=datetime(2026, 5, 9, 10, tzinfo=UTC),
        )
        session.flush()
        _seed_decision(
            session,
            item_id=1,
            ring=RadarRing.WATCH,
            tracks=[],
            reason="r1",
            created_at=datetime(2026, 5, 11, 12, tzinfo=UTC),
        )
        _seed_decision(
            session,
            item_id=2,
            ring=RadarRing.WATCH,
            tracks=[],
            reason="r2",
            created_at=datetime(2026, 5, 9, 12, tzinfo=UTC),
        )

    one = client.get("/api/decisions", params={"date": "2026-05-11", "days": 1})
    assert one.status_code == 200
    assert {row["item_id"] for row in one.json()["rows"]} == {1}

    three = client.get("/api/decisions", params={"date": "2026-05-11", "days": 3})
    assert three.status_code == 200
    assert {row["item_id"] for row in three.json()["rows"]} == {1, 2}


def test_digest_empty(client):
    response = client.get("/api/digest", params={"date": "2026-05-11"})
    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-05-11"
    assert body["days"] == 1
    sections = body["sections"]
    for key in ("Use", "Prototype", "Evaluate", "Watch", "Ignore", "Uncertainty"):
        assert sections[key] == []


def test_digest_populated(client, api_db):
    _db_path, engine = api_db
    published = datetime(2026, 5, 11, 10, tzinfo=UTC)
    decided = datetime(2026, 5, 11, 12, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(session, item_id=1, title="Use Item", published=published)
        _seed_item(session, item_id=2, title="Uncertain Watch", published=published)
        session.flush()
        _seed_decision(
            session,
            item_id=1,
            ring=RadarRing.USE,
            tracks=["Calibration"],
            reason="ship",
            created_at=decided,
        )
        _seed_decision(
            session,
            item_id=2,
            ring=RadarRing.WATCH,
            tracks=[],
            reason="needs more evidence",
            created_at=decided,
            uncertain=True,
        )

    response = client.get("/api/digest", params={"date": "2026-05-11"})
    assert response.status_code == 200
    sections = response.json()["sections"]
    assert [row["item_id"] for row in sections["Use"]] == [1]
    assert [row["item_id"] for row in sections["Watch"]] == [2]
    assert [row["item_id"] for row in sections["Uncertainty"]] == [2]


def test_board_groups_by_ring(client, api_db):
    _db_path, engine = api_db
    published = datetime(2026, 5, 11, 10, tzinfo=UTC)
    decided = datetime(2026, 5, 11, 12, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(session, item_id=1, title="Use Item", published=published)
        _seed_item(session, item_id=2, title="Watch Item", published=published)
        _seed_item(session, item_id=3, title="Ignore Item", published=published)
        session.flush()
        _seed_decision(
            session,
            item_id=1,
            ring=RadarRing.USE,
            tracks=[],
            reason="ship",
            created_at=decided,
        )
        _seed_decision(
            session,
            item_id=2,
            ring=RadarRing.WATCH,
            tracks=[],
            reason="watch",
            created_at=decided,
        )
        _seed_decision(
            session,
            item_id=3,
            ring=RadarRing.IGNORE,
            tracks=[],
            reason="noise",
            created_at=decided,
        )

    response = client.get("/api/board", params={"date": "2026-05-11", "days": 7})
    assert response.status_code == 200
    rings = response.json()["rings"]
    assert [row["item_id"] for row in rings["Use"]] == [1]
    assert [row["item_id"] for row in rings["Watch"]] == [2]
    assert [row["item_id"] for row in rings["Ignore"]] == [3]
    assert rings["Prototype"] == []
    assert rings["Evaluate"] == []


def test_tracks_reflects_config(client, app_config):
    response = client.get("/api/tracks")
    assert response.status_code == 200
    tracks = response.json()["tracks"]
    config_ids = {track.id for track in app_config.topics.tracks}
    api_ids = {track["id"] for track in tracks}
    assert api_ids == config_ids


def test_sources_endpoint(client, app_config):
    response = client.get("/api/sources")
    assert response.status_code == 200
    sources = response.json()["sources"]
    config_ids = {source.id for source in app_config.sources.sources}
    api_ids = {source["id"] for source in sources}
    assert api_ids == config_ids
    for entry in sources:
        for key in ("id", "name", "kind", "enabled", "priority"):
            assert key in entry
