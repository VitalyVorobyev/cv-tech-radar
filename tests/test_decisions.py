from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from radar.db import session_scope
from radar.decisions import DecisionError, list_decisions_for_date, parse_tracks, record_decision
from radar.filters.keyword_filter import classify_items_for_date
from radar.models import Item, RadarDecision
from radar.schemas import RadarRing


def add_decision_item(db_engine, app_config) -> int:
    with session_scope(db_engine) as session:
        item = Item(
            type="paper",
            title="Camera Calibration with Bundle Adjustment",
            normalized_title="camera calibration with bundle adjustment",
            abstract_or_summary="Subpixel calibration target detection for industrial cameras.",
            url="https://example.test/a",
            pdf_url=None,
            published_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
            updated_at=None,
            source_name="arXiv cs.CV",
            external_id="decision-a",
            arxiv_id="decision-a",
            authors_json=[],
            organizations_json=[],
            metadata_json={},
        )
        session.add(item)
        session.flush()
        item_id = item.id
        classify_items_for_date(session, app_config, datetime(2026, 5, 10).date())
    return item_id


def test_record_decision_defaults_to_classifier_tracks(db_engine, app_config):
    item_id = add_decision_item(db_engine, app_config)
    with session_scope(db_engine) as session:
        decision = record_decision(
            session,
            item_id=item_id,
            ring=RadarRing.WATCH,
            tracks=None,
            reason="Relevant but needs more evidence.",
            action="Read PDF later.",
            decided_by="tester",
        )
        assert decision.id is not None
        assert decision.tracks_json

    with session_scope(db_engine) as session:
        stored = session.scalar(select(RadarDecision).where(RadarDecision.item_id == item_id))
        assert stored is not None
        assert stored.ring == "Watch"
        assert stored.decision_reason == "Relevant but needs more evidence."
        rows = list_decisions_for_date(session, datetime(2026, 5, 10).date())
        assert len(rows) == 1
        assert rows[0][1].action == "Read PDF later."


def test_record_decision_rejects_unknown_item(db_engine):
    with session_scope(db_engine) as session, pytest.raises(DecisionError):
        record_decision(
            session,
            item_id=999,
            ring=RadarRing.IGNORE,
            tracks=[],
            reason="No item.",
            action="",
            decided_by="tester",
        )


def test_parse_tracks():
    assert parse_tracks(None) is None
    assert parse_tracks("Object Tracking, Edge AI & Deployment") == [
        "Object Tracking",
        "Edge AI & Deployment",
    ]
