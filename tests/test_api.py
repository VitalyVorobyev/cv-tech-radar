from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.db import session_scope
from radar.filters.keyword_filter import classify_items_for_date
from radar.models import Item, ItemLLMJudgment, RadarDecision
from radar.schemas import RadarRing
from radar.utils import utc_now


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


def test_queue_includes_llm_judgment_when_present(client, api_db, app_config):
    _db_path, engine = api_db
    target = date(2026, 5, 11)
    published = datetime(2026, 5, 11, 10, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(
            session, item_id=1, title="Subpixel checkerboard calibration", published=published
        )
        session.flush()
        classify_items_for_date(session, app_config, target)
        session.add(
            ItemLLMJudgment(
                item_id=1,
                model="gemma-test",
                decision="yes",
                reason="On-topic for calibration.",
                raw_response="DECISION: yes",
                created_at=datetime(2026, 5, 11, 12, tzinfo=UTC),
            )
        )

    response = client.get("/api/queue", params={"date": "2026-05-11"})
    candidate = response.json()["candidates"][0]
    assert candidate["llm_judgment"] is not None
    assert candidate["llm_judgment"]["verdict"] == "yes"
    assert candidate["llm_judgment"]["model"] == "gemma-test"
    assert candidate["llm_judgment"]["reason"] == "On-topic for calibration."


def test_queue_llm_judgment_null_when_absent(client, api_db, app_config):
    _db_path, engine = api_db
    target = date(2026, 5, 11)
    published = datetime(2026, 5, 11, 10, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(
            session, item_id=1, title="Subpixel checkerboard calibration", published=published
        )
        session.flush()
        classify_items_for_date(session, app_config, target)

    response = client.get("/api/queue", params={"date": "2026-05-11"})
    candidate = response.json()["candidates"][0]
    assert candidate["llm_judgment"] is None


def test_board_includes_llm_judgment_when_present(client, api_db):
    _db_path, engine = api_db
    published = datetime(2026, 5, 11, 10, tzinfo=UTC)
    decided = datetime(2026, 5, 11, 12, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(session, item_id=1, title="Subpixel calibration", published=published)
        session.flush()
        _seed_decision(
            session,
            item_id=1,
            ring=RadarRing.USE,
            tracks=[],
            reason="ship",
            created_at=decided,
        )
        session.add(
            ItemLLMJudgment(
                item_id=1,
                model="gemma-test",
                decision="yes",
                reason="agrees with curator",
                raw_response="DECISION: yes",
                created_at=datetime(2026, 5, 11, 13, tzinfo=UTC),
            )
        )

    response = client.get("/api/board")
    rings = response.json()["rings"]
    assert rings["Use"][0]["llm_judgment"]["verdict"] == "yes"


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

    # Default: Ignore is hidden but its count is reported in the counts envelope.
    response = client.get("/api/board")
    assert response.status_code == 200
    body = response.json()
    rings = body["rings"]
    counts = body["counts"]
    assert [row["item_id"] for row in rings["Use"]] == [1]
    assert [row["item_id"] for row in rings["Watch"]] == [2]
    assert rings["Ignore"] == []
    assert rings["Prototype"] == []
    assert rings["Evaluate"] == []
    assert counts == {"Use": 1, "Prototype": 0, "Evaluate": 0, "Watch": 1, "Ignore": 1}

    # decided_at populated on each row.
    use_row = rings["Use"][0]
    assert use_row["decided_at"].startswith("2026-05-11")
    assert use_row["score"] is None  # no classification was run

    # include_ignore exposes the slush pile.
    response = client.get("/api/board", params={"include_ignore": "true"})
    rings = response.json()["rings"]
    assert [row["item_id"] for row in rings["Ignore"]] == [3]


def test_board_returns_latest_decision_regardless_of_publish_date(client, api_db):
    """A paper decided weeks ago must still appear on the persistent board."""
    _db_path, engine = api_db
    old_published = datetime(2026, 3, 1, 10, tzinfo=UTC)
    old_decided = datetime(2026, 3, 2, 10, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(session, item_id=10, title="Old Use Item", published=old_published)
        session.flush()
        _seed_decision(
            session,
            item_id=10,
            ring=RadarRing.USE,
            tracks=["Calibration"],
            reason="still relevant",
            created_at=old_decided,
        )

    response = client.get("/api/board")
    rings = response.json()["rings"]
    assert [row["item_id"] for row in rings["Use"]] == [10]


def test_board_latest_decision_supersedes_earlier(client, api_db):
    _db_path, engine = api_db
    published = datetime(2026, 5, 1, 10, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(session, item_id=42, title="Reclassified Item", published=published)
        session.flush()
        _seed_decision(
            session,
            item_id=42,
            ring=RadarRing.WATCH,
            tracks=[],
            reason="initial watch",
            created_at=datetime(2026, 5, 2, 9, tzinfo=UTC),
        )
        _seed_decision(
            session,
            item_id=42,
            ring=RadarRing.USE,
            tracks=[],
            reason="promoted",
            created_at=datetime(2026, 5, 10, 9, tzinfo=UTC),
        )

    response = client.get("/api/board")
    rings = response.json()["rings"]
    assert rings["Watch"] == []
    assert [row["item_id"] for row in rings["Use"]] == [42]
    assert rings["Use"][0]["reason"] == "promoted"


def test_board_breaks_ties_on_decision_id(client, api_db):
    """When two decisions share created_at, the higher-id row wins in rings AND counts."""
    _db_path, engine = api_db
    published = datetime(2026, 5, 1, 10, tzinfo=UTC)
    tied_at = datetime(2026, 5, 9, 12, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(session, item_id=7, title="Tied Item", published=published)
        session.flush()
        # First insert → smaller id, ring=Watch.
        _seed_decision(
            session,
            item_id=7,
            ring=RadarRing.WATCH,
            tracks=[],
            reason="earlier",
            created_at=tied_at,
        )
        session.flush()
        # Second insert → larger id, same timestamp, ring=Use.
        _seed_decision(
            session,
            item_id=7,
            ring=RadarRing.USE,
            tracks=[],
            reason="later",
            created_at=tied_at,
        )

    response = client.get("/api/board")
    body = response.json()
    assert body["rings"]["Watch"] == []
    assert [row["item_id"] for row in body["rings"]["Use"]] == [7]
    assert body["rings"]["Use"][0]["reason"] == "later"
    # counts must match rings — no double-counting from the tied row.
    assert body["counts"]["Use"] == 1
    assert body["counts"]["Watch"] == 0


def test_board_decided_since_filter(client, api_db):
    _db_path, engine = api_db
    published = datetime(2026, 5, 1, 10, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(session, item_id=1, title="Old", published=published)
        _seed_item(session, item_id=2, title="Fresh", published=published)
        session.flush()
        _seed_decision(
            session,
            item_id=1,
            ring=RadarRing.USE,
            tracks=[],
            reason="old",
            created_at=datetime(2026, 3, 1, 10, tzinfo=UTC),
        )
        _seed_decision(
            session,
            item_id=2,
            ring=RadarRing.USE,
            tracks=[],
            reason="fresh",
            created_at=datetime(2026, 5, 10, 10, tzinfo=UTC),
        )

    response = client.get("/api/board", params={"decided_since": "2026-05-01T00:00:00+00:00"})
    rings = response.json()["rings"]
    assert [row["item_id"] for row in rings["Use"]] == [2]


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


def test_get_item_happy_path_with_history_and_movement(client, api_db):
    _db_path, engine = api_db
    published = datetime(2026, 5, 1, 10, tzinfo=UTC)
    # First decision must be outside the 7-day window so "new" precedence
    # does not pre-empt the "in" classification we want to assert on.
    now = utc_now()
    first_decided = now - timedelta(days=30)
    second_decided = now - timedelta(days=1)
    with session_scope(engine) as session:
        _seed_item(session, item_id=7, title="Calibration paper", published=published)
        session.flush()
        item = session.get(Item, 7)
        assert item is not None
        item.first_decided_at = first_decided
        session.add(
            RadarDecision(
                item_id=7,
                ring=RadarRing.WATCH.value,
                tracks_json=["Calibration & Camera Models"],
                decision_reason="initial watch",
                action="",
                decided_by="tester",
                uncertain=False,
                previous_ring=None,
                created_at=first_decided,
            )
        )
        session.add(
            RadarDecision(
                item_id=7,
                ring=RadarRing.USE.value,
                tracks_json=["Calibration & Camera Models"],
                decision_reason="promoted to Use",
                action="ship it",
                decided_by="tester",
                uncertain=False,
                previous_ring=RadarRing.WATCH.value,
                created_at=second_decided,
            )
        )

    response = client.get("/api/items/7")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 7
    assert body["title"] == "Calibration paper"
    assert body["abstract"].startswith("Camera calibration")
    assert body["ring"] == "Use"
    assert body["track"] == "Calibration & Camera Models"
    assert body["tracks"] == ["Calibration & Camera Models"]
    assert body["reason"] == "promoted to Use"
    assert body["uncertain"] is False
    assert body["source"] == "arXiv cs.CV"
    assert body["decided_by"] == "tester"
    history = body["history"]
    assert [entry["ring"] for entry in history] == ["Watch", "Use"]
    assert body["movement"] == "in"


def test_get_item_returns_404_for_unknown_id(client):
    response = client.get("/api/items/9999")
    assert response.status_code == 404


def test_get_item_no_decisions_returns_empty_ring(client, api_db):
    _db_path, engine = api_db
    published = datetime(2026, 5, 1, 10, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(session, item_id=11, title="Uncurated", published=published)

    response = client.get("/api/items/11")
    assert response.status_code == 200
    body = response.json()
    assert body["ring"] == ""
    assert body["history"] == []
    assert body["movement"] is None
    assert body["track"] == ""
    assert body["tracks"] == []
    assert body["decided_by"] is None


def test_timeline_returns_requested_weeks_with_correct_buckets(client, api_db):
    _db_path, engine = api_db
    now = utc_now()
    today = now.date()
    this_monday = datetime(today.year, today.month, today.day, tzinfo=UTC) - timedelta(
        days=today.weekday()
    )
    # Three items, each in a distinct ISO week within the 4-week window.
    week0 = this_monday + timedelta(days=2)  # current week
    week1 = this_monday - timedelta(weeks=1) + timedelta(days=1)
    week3 = this_monday - timedelta(weeks=3) + timedelta(days=3)

    published = datetime(2026, 1, 1, 10, tzinfo=UTC)
    with session_scope(engine) as session:
        for idx, decided_at, ring in [
            (1, week0, RadarRing.USE),
            (2, week1, RadarRing.EVALUATE),
            (3, week3, RadarRing.WATCH),
        ]:
            _seed_item(session, item_id=idx, title=f"item-{idx}", published=published)
            session.flush()
            item = session.get(Item, idx)
            assert item is not None
            item.first_decided_at = decided_at
            session.add(
                RadarDecision(
                    item_id=idx,
                    ring=ring.value,
                    tracks_json=[],
                    decision_reason="seed",
                    action="",
                    decided_by="tester",
                    uncertain=False,
                    previous_ring=None,
                    created_at=decided_at,
                )
            )

    response = client.get("/api/timeline", params={"weeks": 4})
    assert response.status_code == 200
    body = response.json()
    weeks = body["weeks"]
    assert len(weeks) == 4

    # Chronologically ordered: oldest first.
    iso_keys = [w["iso"] for w in weeks]
    assert iso_keys == sorted(iso_keys)

    def _iso_for(moment: datetime) -> str:
        iso = moment.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    by_iso = {w["iso"]: w for w in weeks}
    assert by_iso[_iso_for(week0)]["Use"] == 1
    assert by_iso[_iso_for(week1)]["Evaluate"] == 1
    assert by_iso[_iso_for(week3)]["Watch"] == 1
    # Buckets that should NOT be incremented.
    assert by_iso[_iso_for(week0)]["Watch"] == 0
    assert by_iso[_iso_for(week1)]["Use"] == 0


def test_board_items_include_movement_field(client, api_db):
    _db_path, engine = api_db
    published = datetime(2026, 5, 1, 10, tzinfo=UTC)
    now = utc_now()
    # first_decided_at outside 7d window so "new" doesn't pre-empt "in".
    first_decided = now - timedelta(days=30)
    second_decided = now - timedelta(days=1)
    with session_scope(engine) as session:
        _seed_item(session, item_id=20, title="Promoted item", published=published)
        session.flush()
        item = session.get(Item, 20)
        assert item is not None
        item.first_decided_at = first_decided
        session.add(
            RadarDecision(
                item_id=20,
                ring=RadarRing.WATCH.value,
                tracks_json=[],
                decision_reason="initial",
                action="",
                decided_by="tester",
                uncertain=False,
                previous_ring=None,
                created_at=first_decided,
            )
        )
        session.add(
            RadarDecision(
                item_id=20,
                ring=RadarRing.USE.value,
                tracks_json=[],
                decision_reason="promoted",
                action="",
                decided_by="tester",
                uncertain=False,
                previous_ring=RadarRing.WATCH.value,
                created_at=second_decided,
            )
        )

    response = client.get("/api/board")
    assert response.status_code == 200
    rings = response.json()["rings"]
    use_rows = rings["Use"]
    assert use_rows, "expected at least one Use row"
    target = next(row for row in use_rows if row["item_id"] == 20)
    assert "movement" in target
    # Promotion within the 7-day window -> "in".
    assert target["movement"] == "in"
    # All rows must have the movement key (even if None).
    for ring_rows in rings.values():
        for row in ring_rows:
            assert "movement" in row
