"""Tests for ``collect_content_dates`` — the Queue/Digest date-grid backing."""

from __future__ import annotations

from datetime import UTC, datetime

from radar.db import session_scope
from radar.models import Digest, Item, ItemClassification, RadarDecision
from radar.reports.content_dates import collect_content_dates


def _add_item(session, *, item_id: int, published: datetime) -> None:
    session.add(
        Item(
            id=item_id,
            type="paper",
            title=f"Item {item_id}",
            normalized_title=f"item {item_id}",
            abstract_or_summary="",
            url=f"https://example.test/{item_id}",
            pdf_url=None,
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


def _classify(session, item_id: int) -> None:
    session.add(ItemClassification(item_id=item_id, recommended_ring="Watch"))


def _decide(session, item_id: int) -> None:
    session.add(
        RadarDecision(
            item_id=item_id,
            ring="Watch",
            tracks_json=[],
            decision_reason="r",
            action="",
            decided_by="tester",
            created_at=datetime(2026, 5, 17, 9, 0, tzinfo=UTC),
        )
    )


def test_collect_content_dates_groups_queue_by_published_day(db_engine):
    day_a = datetime(2026, 5, 16, 10, 0, tzinfo=UTC)
    day_b = datetime(2026, 5, 14, 10, 0, tzinfo=UTC)
    with session_scope(db_engine) as session:
        # Day A: two classified items, one of them decided.
        _add_item(session, item_id=1, published=day_a)
        _add_item(session, item_id=2, published=day_a)
        # Day B: one classified item.
        _add_item(session, item_id=3, published=day_b)
        # An unclassified item must not create a queue day.
        _add_item(session, item_id=4, published=datetime(2026, 5, 10, tzinfo=UTC))
        session.flush()
        for item_id in (1, 2, 3):
            _classify(session, item_id)
        _decide(session, 1)

    with session_scope(db_engine) as session:
        dates = collect_content_dates(session)

    # Newest-first; only days with classified items appear.
    assert [entry.date for entry in dates.queue] == ["2026-05-16", "2026-05-14"]
    day_a_entry = dates.queue[0]
    assert day_a_entry.candidate_count == 2
    assert day_a_entry.decided_count == 1
    assert dates.queue[1].candidate_count == 1
    assert dates.queue[1].decided_count == 0


def test_collect_content_dates_lists_digest_days(db_engine):
    with session_scope(db_engine) as session:
        _add_item(session, item_id=1, published=datetime(2026, 5, 16, 10, 0, tzinfo=UTC))
        session.flush()
        _decide(session, 1)
        session.add(
            Digest(
                kind="daily",
                date="2026-05-16",
                title="Daily Digest 2026-05-16",
                markdown_path="reports/digests/2026-05-16.md",
                json_path=None,
            )
        )
        session.add(
            Digest(
                kind="daily",
                date="2026-05-12",
                title="Daily Digest 2026-05-12",
                markdown_path="reports/digests/2026-05-12.md",
                json_path=None,
            )
        )

    with session_scope(db_engine) as session:
        dates = collect_content_dates(session)

    assert [entry.date for entry in dates.digest] == ["2026-05-16", "2026-05-12"]
    assert dates.digest[0].title == "Daily Digest 2026-05-16"
    assert dates.digest[0].item_count == 1
    assert dates.digest[1].item_count == 0


def test_collect_content_dates_empty_db(db_engine):
    with session_scope(db_engine) as session:
        dates = collect_content_dates(session)
    assert dates.queue == []
    assert dates.digest == []
