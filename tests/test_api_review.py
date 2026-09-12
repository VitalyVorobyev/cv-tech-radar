"""The review inbox API — filters, ordering, and the bulk actions.

Gate *enforcement* is covered in tests/test_review_gate.py; this file covers
the inbox itself as a working surface for a several-hundred-item backlog.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.db import ensure_sources, get_engine, init_db, session_scope
from radar.decisions import record_decision
from radar.models import Item
from radar.schemas import DecisionOrigin, RadarRing


@pytest.fixture
def api_db(tmp_path, app_config):
    db_path = tmp_path / "review.sqlite"
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


def _propose(
    engine,
    *,
    item_id: int,
    title: str,
    ring: RadarRing,
    tracks: list[str],
    origin: DecisionOrigin = DecisionOrigin.AGENT,
) -> None:
    with session_scope(engine) as session:
        if session.get(Item, item_id) is None:
            session.add(
                Item(
                    id=item_id,
                    type="paper",
                    title=title,
                    normalized_title=title.lower(),
                    abstract_or_summary="abstract",
                    url=f"https://example.test/{item_id}",
                    pdf_url=None,
                    published_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
                    updated_at=None,
                    source_name="arXiv cs.CV",
                    external_id=f"ext-{item_id}",
                    arxiv_id=f"ext-{item_id}",
                    authors_json=[],
                    organizations_json=[],
                    metadata_json={},
                )
            )
            session.flush()
        record_decision(
            session,
            item_id=item_id,
            ring=ring,
            tracks=tracks,
            reason=f"proposal for {item_id}",
            action="",
            decided_by="claude-curator",
            origin=origin,
        )


def _seed_backlog(engine) -> None:
    _propose(engine, item_id=1, title="Alpha use", ring=RadarRing.USE, tracks=["Calibration"])
    _propose(engine, item_id=2, title="Beta watch", ring=RadarRing.WATCH, tracks=["Tracking"])
    _propose(
        engine, item_id=3, title="Gamma evaluate", ring=RadarRing.EVALUATE, tracks=["Calibration"]
    )
    _propose(engine, item_id=4, title="Delta ignore", ring=RadarRing.IGNORE, tracks=["Tracking"])


def test_inbox_orders_by_ring_then_score(client, api_db):
    _db_path, engine = api_db
    _seed_backlog(engine)

    body = client.get("/api/review").json()
    # Ignore is excluded by default; the rest run most-attention-first.
    assert [row["id"] for row in body["items"]] == [1, 3, 2]
    assert body["pending_total"] == 3
    assert body["counts"] == {
        "Use": 1,
        "Prototype": 0,
        "Evaluate": 1,
        "Watch": 1,
        "Ignore": 1,
    }


def test_inbox_filters(client, api_db):
    _db_path, engine = api_db
    _seed_backlog(engine)

    by_ring = client.get("/api/review", params={"ring": "Watch"}).json()
    assert [row["id"] for row in by_ring["items"]] == [2]

    by_track = client.get("/api/review", params={"track": "Calibration"}).json()
    assert [row["id"] for row in by_track["items"]] == [1, 3]

    by_query = client.get("/api/review", params={"q": "gamma"}).json()
    assert [row["id"] for row in by_query["items"]] == [3]

    with_ignore = client.get("/api/review", params={"include_ignore": True}).json()
    assert with_ignore["pending_total"] == 4


def test_inbox_paginates(client, api_db):
    _db_path, engine = api_db
    _seed_backlog(engine)

    page = client.get("/api/review", params={"limit": 2, "offset": 0}).json()
    assert [row["id"] for row in page["items"]] == [1, 3]
    # pending_total is the full backlog, not the page — it drives "N remaining".
    assert page["pending_total"] == 3

    rest = client.get("/api/review", params={"limit": 2, "offset": 2}).json()
    assert [row["id"] for row in rest["items"]] == [2]


def test_inbox_payload_carries_proposal_and_scores(client, api_db):
    _db_path, engine = api_db
    _propose(engine, item_id=1, title="Alpha", ring=RadarRing.USE, tracks=["Calibration"])

    row = client.get("/api/review").json()["items"][0]
    assert row["title"] == "Alpha"
    assert row["proposal"]["ring"] == "Use"
    assert row["proposal"]["decided_by"] == "claude-curator"
    assert row["proposal"]["reason"] == "proposal for 1"
    assert row["previous_confirmed_ring"] is None
    assert set(row["scores"]) == {
        "relevance",
        "source_priority",
        "implementation",
        "attention",
        "novelty",
        "negative_penalty",
        "final",
    }


def test_overriding_the_ring_clears_the_item_from_the_inbox(client, api_db):
    _db_path, engine = api_db
    _propose(engine, item_id=1, title="Alpha", ring=RadarRing.USE, tracks=["Calibration"])

    post = client.post(
        "/api/decisions",
        json={"item_id": 1, "ring": "Watch", "reason": "Overridden on review."},
    )
    assert post.status_code == 201, post.text

    assert client.get("/api/review").json()["pending_total"] == 0
    board = client.get("/api/board").json()
    assert [row["item_id"] for row in board["rings"]["Watch"]] == [1]
    assert board["rings"]["Use"] == []


def test_confirm_unknown_decision_is_404(client):
    assert client.post("/api/review/confirm", json={"decision_id": 4242}).status_code == 404


def test_bulk_endpoints_reject_empty_lists(client):
    assert client.post("/api/review/confirm-bulk", json={"decision_ids": []}).status_code == 422
    assert client.post("/api/review/dismiss-bulk", json={"item_ids": []}).status_code == 422


def test_dismiss_bulk_uses_a_default_reason(client, api_db):
    _db_path, engine = api_db
    _propose(engine, item_id=1, title="Alpha", ring=RadarRing.USE, tracks=["Calibration"])

    assert client.post("/api/review/dismiss-bulk", json={"item_ids": [1]}).status_code == 200
    detail = client.get("/api/items/1").json()
    assert detail["reason"] == "Dismissed in review."


def test_summary_counts_both_lanes(client, api_db):
    _db_path, engine = api_db
    _seed_backlog(engine)

    summary = client.get("/api/review/summary").json()
    # Ignore proposals are not part of the working backlog.
    assert summary["papers_pending"] == 3
    assert summary["ecosystem_pending"] == 0
