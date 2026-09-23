"""The manual gate: an unratified proposal must not reach any radar surface.

Every public surface is asserted from one seeded fixture so that a surface
added later — or an existing one that forgets to join through
``latest_confirmed_decision_subq`` — fails here rather than silently leaking
an unreviewed item onto the radar.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from radar.api.app import create_app
from radar.db import ensure_sources, get_engine, init_db, session_scope
from radar.decisions import confirm_decision, record_decision
from radar.models import Item, RadarDecision
from radar.reports.content_dates import collect_content_dates
from radar.reports.digest import collect_board_rows, collect_digest_rows, render_digest_markdown
from radar.reports.static_bundle import build_static_bundle
from radar.schemas import DecisionOrigin, RadarRing

PUBLISHED = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
TITLE = "Unreviewed Proposal Paper"


def _as_utc(moment: datetime | None) -> datetime | None:
    """SQLite drops tzinfo on read; normalise for equality checks."""
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=UTC)


@pytest.fixture
def api_db(tmp_path, app_config):
    db_path = tmp_path / "gate.sqlite"
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


def _seed_proposal(engine, *, ring: RadarRing = RadarRing.USE) -> tuple[int, int]:
    """Seed one item with a single unratified agent proposal at `ring`."""
    with session_scope(engine) as session:
        item = Item(
            type="paper",
            title=TITLE,
            normalized_title=TITLE.lower(),
            abstract_or_summary="Camera calibration for industrial inspection rigs.",
            url="https://example.test/pending",
            pdf_url=None,
            published_at=PUBLISHED,
            updated_at=None,
            source_name="arXiv cs.CV",
            external_id="pending-1",
            arxiv_id="pending-1",
            authors_json=[],
            organizations_json=[],
            metadata_json={},
        )
        session.add(item)
        session.flush()
        decision = record_decision(
            session,
            item_id=item.id,
            ring=ring,
            tracks=["Calibration & Camera Models"],
            reason="Looks strong.",
            action="",
            decided_by="claude-curator",
            origin=DecisionOrigin.AGENT,
        )
        return item.id, decision.id


def test_agent_proposal_is_recorded_but_unconfirmed(db_engine):
    item_id, decision_id = _seed_proposal(db_engine)
    with session_scope(db_engine) as session:
        stored = session.get(RadarDecision, decision_id)
        assert stored is not None
        assert stored.origin == "agent"
        assert stored.confirmed_at is None
        assert stored.confirmed_by is None
        # An unconfirmed proposal must not look like radar entry.
        assert session.get(Item, item_id).first_decided_at is None


def test_human_decision_confirms_itself(db_engine):
    item_id, _ = _seed_proposal(db_engine)
    with session_scope(db_engine) as session:
        decision = record_decision(
            session,
            item_id=item_id,
            ring=RadarRing.WATCH,
            tracks=None,
            reason="Downgraded on review.",
            action="",
            decided_by="web-curator",
            origin=DecisionOrigin.HUMAN,
        )
        assert decision.confirmed_at == decision.created_at
        assert decision.confirmed_by == "web-curator"
        assert _as_utc(session.get(Item, item_id).first_decided_at) == decision.created_at


def test_confirm_is_idempotent_and_stamps_first_decided_at(db_engine):
    item_id, decision_id = _seed_proposal(db_engine)
    with session_scope(db_engine) as session:
        first = confirm_decision(session, decision_id=decision_id, confirmed_by="me")
        stamped = first.confirmed_at
        again = confirm_decision(session, decision_id=decision_id, confirmed_by="someone-else")
        assert again.confirmed_at == stamped
        assert again.confirmed_by == "me"
        assert _as_utc(session.get(Item, item_id).first_decided_at) == stamped


@pytest.mark.parametrize("ring", [RadarRing.USE, RadarRing.PROTOTYPE, RadarRing.WATCH])
def test_board_hides_unconfirmed_proposal_at_any_ring(db_engine, ring):
    _seed_proposal(db_engine, ring=ring)
    with session_scope(db_engine) as session:
        assert collect_board_rows(session) == []
        assert collect_board_rows(session, include_ignore=True) == []


def test_api_surfaces_hide_unconfirmed_proposal(client, api_db):
    _db_path, engine = api_db
    item_id, decision_id = _seed_proposal(engine)

    board = client.get("/api/board").json()
    assert all(board["rings"][ring] == [] for ring in board["rings"])
    assert all(count == 0 for count in board["counts"].values())

    # The item detail resolves, but reports no ring and offers the proposal.
    detail = client.get(f"/api/items/{item_id}").json()
    assert detail["ring"] == ""
    assert detail["history"] == []
    assert detail["pending_proposal"]["decision_id"] == decision_id
    assert detail["pending_proposal"]["decided_by"] == "claude-curator"

    assert client.get("/api/timeline").json()["weeks"] == [] or all(
        week["Use"] == 0 for week in client.get("/api/timeline").json()["weeks"]
    )

    # ...and it is waiting in the review inbox.
    review = client.get("/api/review").json()
    assert review["pending_total"] == 1
    assert review["items"][0]["proposal"]["decision_id"] == decision_id
    assert review["counts"]["Use"] == 1
    assert client.get("/api/review/summary").json()["papers_pending"] == 1


def test_digest_and_content_dates_hide_unconfirmed_proposal(db_engine):
    _seed_proposal(db_engine)
    with session_scope(db_engine) as session:
        rows = collect_digest_rows(session, PUBLISHED.date(), 1)
        assert rows == []
        markdown = render_digest_markdown(rows, PUBLISHED.date(), 1)
        assert TITLE not in markdown

        dates = collect_content_dates(session)
        decided = {entry.date: entry.decided_count for entry in dates.queue}
        assert decided.get(PUBLISHED.date().isoformat(), 0) == 0


def test_static_bundle_does_not_leak_unconfirmed_proposal(db_engine, app_config, tmp_path):
    """The static bundle is the public GitHub Pages surface — the critical one."""
    item_id, _ = _seed_proposal(db_engine)
    target = tmp_path / "bundle"
    with session_scope(db_engine) as session:
        build_static_bundle(target, session=session, config=app_config, weeks=4)

    board = json.loads((target / "board.json").read_text())
    assert sum(len(v) for v in board["rings"].values()) == 0

    # The bundle only ships detail files for items on the board, so an
    # unreviewed item has no published page at all.
    assert not (target / "items" / f"{item_id}.json").exists()
    # And its reason must not appear anywhere in the bundle.
    for path in target.rglob("*.json"):
        assert "Looks strong." not in path.read_text()
        assert TITLE not in path.read_text()


def test_confirming_puts_the_item_on_every_surface(client, api_db, app_config, tmp_path):
    _db_path, engine = api_db
    item_id, decision_id = _seed_proposal(engine)

    post = client.post("/api/review/confirm", json={"decision_id": decision_id})
    assert post.status_code == 200, post.text
    assert post.json()["ring"] == "Use"

    board = client.get("/api/board").json()
    assert [row["item_id"] for row in board["rings"]["Use"]] == [item_id]
    assert board["counts"]["Use"] == 1

    detail = client.get(f"/api/items/{item_id}").json()
    assert detail["ring"] == "Use"
    assert detail["pending_proposal"] is None
    assert [entry["ring"] for entry in detail["history"]] == ["Use"]

    assert client.get("/api/review").json()["pending_total"] == 0

    with session_scope(engine) as session:
        rows = collect_digest_rows(session, PUBLISHED.date(), 1)
        assert [item.id for item, _ in rows] == [item_id]
        build_static_bundle(tmp_path / "b", session=session, config=app_config, weeks=4)
    board_json = json.loads((tmp_path / "b" / "board.json").read_text())
    assert [row["item_id"] for row in board_json["rings"]["Use"]] == [item_id]


def test_reapplying_a_proposal_does_not_unconfirm_or_duplicate(client, api_db):
    """Re-running `radar apply` over the same candidates is a no-op for the radar."""
    _db_path, engine = api_db
    item_id, decision_id = _seed_proposal(engine)
    client.post("/api/review/confirm", json={"decision_id": decision_id})

    with session_scope(engine) as session:
        record_decision(
            session,
            item_id=item_id,
            ring=RadarRing.EVALUATE,
            tracks=None,
            reason="Re-proposed by a later apply run.",
            action="",
            decided_by="claude-curator",
            origin=DecisionOrigin.AGENT,
        )

    board = client.get("/api/board").json()
    # Still exactly one blip, still at the confirmed ring — the newer proposal
    # does not supersede a human decision until someone confirms it.
    assert [row["item_id"] for row in board["rings"]["Use"]] == [item_id]
    assert board["rings"]["Evaluate"] == []
    # ...and the re-proposal is queued for review.
    review = client.get("/api/review").json()
    assert review["pending_total"] == 1
    assert review["items"][0]["previous_confirmed_ring"] == "Use"


def test_dismiss_bulk_records_a_human_ignore(client, api_db):
    _db_path, engine = api_db
    item_id, _ = _seed_proposal(engine)

    post = client.post("/api/review/dismiss-bulk", json={"item_ids": [item_id]})
    assert post.status_code == 200, post.text
    assert post.json()["dismissed"] == [item_id]

    assert client.get("/api/review").json()["pending_total"] == 0
    board = client.get("/api/board").json()
    assert board["rings"]["Ignore"] == []  # Ignore never renders as a blip
    assert board["counts"]["Ignore"] == 1  # ...but it is a real, counted decision

    with session_scope(engine) as session:
        latest = session.scalars(
            select(RadarDecision)
            .where(RadarDecision.item_id == item_id)
            .order_by(RadarDecision.created_at.desc(), RadarDecision.id.desc())
        ).first()
        assert latest is not None
        assert latest.ring == RadarRing.IGNORE.value
        assert latest.origin == "human"
        assert latest.confirmed_at is not None


def test_confirm_bulk_reports_partial_failure(client, api_db):
    _db_path, engine = api_db
    _item_id, decision_id = _seed_proposal(engine)

    post = client.post(
        "/api/review/confirm-bulk",
        json={"decision_ids": [decision_id, 999_999]},
    )
    assert post.status_code == 200, post.text
    body = post.json()
    assert body["confirmed"] == [decision_id]
    assert [row["decision_id"] for row in body["failed"]] == [999_999]


def test_review_hides_ignore_proposals_by_default(client, api_db):
    _db_path, engine = api_db
    _seed_proposal(engine, ring=RadarRing.IGNORE)

    assert client.get("/api/review").json()["pending_total"] == 0
    assert client.get("/api/review").json()["counts"]["Ignore"] == 1
    assert client.get("/api/review", params={"include_ignore": True}).json()["pending_total"] == 1


def test_movement_uses_confirmation_time(db_engine):
    """A proposal written weeks ago is "new" when it is confirmed, not before."""
    long_ago = datetime.now(tz=UTC) - timedelta(days=90)
    with session_scope(db_engine) as session:
        item = Item(
            type="paper",
            title="Old proposal",
            normalized_title="old proposal",
            abstract_or_summary="",
            url="https://example.test/old",
            pdf_url=None,
            published_at=long_ago,
            updated_at=None,
            source_name="arXiv cs.CV",
            external_id="old-1",
            arxiv_id="old-1",
            authors_json=[],
            organizations_json=[],
            metadata_json={},
        )
        session.add(item)
        session.flush()
        decision = record_decision(
            session,
            item_id=item.id,
            ring=RadarRing.WATCH,
            tracks=["Calibration & Camera Models"],
            reason="Old proposal.",
            action="",
            decided_by="claude-curator",
            origin=DecisionOrigin.AGENT,
        )
        decision.created_at = long_ago
        session.flush()
        confirm_decision(session, decision_id=decision.id, confirmed_by="me")
        refreshed = session.get(Item, item.id)
        assert refreshed is not None
        stamped = _as_utc(refreshed.first_decided_at)
        assert stamped is not None
        assert stamped > long_ago
