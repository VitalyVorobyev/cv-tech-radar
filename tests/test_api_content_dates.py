"""API test for ``GET /api/content-dates``."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.db import ensure_sources, get_engine, init_db, session_scope
from radar.models import Item, ItemClassification, RadarDecision


@pytest.fixture
def api_db(tmp_path, app_config):
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


def test_content_dates_endpoint(client, api_db):
    _db_path, engine = api_db
    with session_scope(engine) as session:
        session.add(
            Item(
                id=1,
                type="paper",
                title="Item 1",
                normalized_title="item 1",
                abstract_or_summary="",
                url="https://example.test/1",
                pdf_url=None,
                published_at=datetime(2026, 5, 16, 10, 0, tzinfo=UTC),
                updated_at=None,
                source_name="arXiv cs.CV",
                external_id="ext-1",
                arxiv_id="ext-1",
                authors_json=[],
                organizations_json=[],
                metadata_json={},
            )
        )
        session.flush()
        session.add(ItemClassification(item_id=1, recommended_ring="Watch"))
        session.add(
            RadarDecision(
                item_id=1,
                ring="Watch",
                tracks_json=[],
                decision_reason="r",
                action="",
                decided_by="tester",
                created_at=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
            )
        )

    response = client.get("/api/content-dates")
    assert response.status_code == 200
    payload = response.json()
    assert payload["queue"] == [{"date": "2026-05-16", "candidate_count": 1, "decided_count": 1}]
    assert payload["digest"] == []
