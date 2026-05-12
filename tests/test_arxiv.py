from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import select

from radar.collectors.arxiv import (
    fetch_and_store_arxiv,
    normalize_arxiv_entry,
    store_normalized_item,
)
from radar.db import session_scope
from radar.models import Item, RawItem, Source
from radar.schemas import ItemType, NormalizedItem


def test_normalize_arxiv_entry_preserves_fields():
    feed_text = Path("tests/fixtures/arxiv_feed.xml").read_text(encoding="utf-8")
    import feedparser

    entry = feedparser.parse(feed_text).entries[0]
    normalized, raw = normalize_arxiv_entry(entry, source_name="arXiv cs.CV", category="cs.CV")
    assert normalized.arxiv_id == "2605.00001"
    assert normalized.pdf_url == "http://arxiv.org/pdf/2605.00001v2"
    assert normalized.authors == ["Ada Vision"]
    assert normalized.published_at == datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    assert "Camera Calibration" in normalized.title
    assert raw["categories"] == ["cs.CV"]


def test_fetch_arxiv_stores_and_dedupes(db_engine, app_config):
    feed_text = Path("tests/fixtures/arxiv_feed.xml").read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["search_query"] == "cat:cs.CV"
        return httpx.Response(200, text=feed_text)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source_config = app_config.sources.sources[0]
    with session_scope(db_engine) as session:
        source = session.scalar(select(Source).where(Source.key == source_config.id))
        stats = fetch_and_store_arxiv(
            session,
            source,
            source_config,
            days=1,
            max_results=10,
            client=client,
            now=datetime(2026, 5, 10, 20, 0, tzinfo=UTC),
        )
        assert stats.stored == 2

    with session_scope(db_engine) as session:
        source = session.scalar(select(Source).where(Source.key == source_config.id))
        stats = fetch_and_store_arxiv(
            session,
            source,
            source_config,
            days=1,
            max_results=10,
            client=client,
            now=datetime(2026, 5, 10, 20, 0, tzinfo=UTC),
        )
        assert stats.stored == 0
        assert stats.updated == 2
        assert session.scalar(select(Item).where(Item.arxiv_id == "2605.00001")) is not None
        assert len(session.scalars(select(Item)).all()) == 2
        assert len(session.scalars(select(RawItem)).all()) == 2


def test_fetch_arxiv_pagination_stops_when_cutoff_hit(db_engine, app_config):
    feed_text = Path("tests/fixtures/arxiv_feed.xml").read_text(encoding="utf-8")
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["start"])
        calls.append(start)
        return httpx.Response(200, text=feed_text)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source_config = app_config.sources.sources[0]
    with session_scope(db_engine) as session:
        source = session.scalar(select(Source).where(Source.key == source_config.id))
        # Cutoff is 2026-05-12, fixture entries are all 2026-05-10, so every entry
        # is below the cutoff and the loop must terminate on the first page.
        stats = fetch_and_store_arxiv(
            session,
            source,
            source_config,
            days=1,
            max_results=2,
            max_pages=5,
            client=client,
            now=datetime(2026, 5, 12, 0, 0, tzinfo=UTC),
        )
    assert calls == [0]
    assert stats.pages == 1
    assert stats.skipped_old == 2
    assert stats.stored == 0


def test_fetch_arxiv_pagination_walks_multiple_pages(db_engine, app_config):
    """When entries fit within --days, walk pages until results are exhausted."""
    feed_text = Path("tests/fixtures/arxiv_feed.xml").read_text(encoding="utf-8")
    empty_feed = (
        '<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["start"])
        # First page (start=0) returns 2 entries; second page (start=2) is empty.
        if start == 0:
            return httpx.Response(200, text=feed_text)
        return httpx.Response(200, text=empty_feed)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source_config = app_config.sources.sources[0]
    with session_scope(db_engine) as session:
        source = session.scalar(select(Source).where(Source.key == source_config.id))
        stats = fetch_and_store_arxiv(
            session,
            source,
            source_config,
            days=30,
            max_results=2,
            max_pages=5,
            page_delay_seconds=0.0,
            client=client,
            now=datetime(2026, 5, 11, 0, 0, tzinfo=UTC),
        )
    # We walk both pages: 2 stored from page 1, 0 from empty page 2.
    assert stats.stored == 2
    assert stats.pages == 2
    assert stats.latest_published_at == datetime(2026, 5, 10, 10, 0, tzinfo=UTC)


def test_fetch_arxiv_sleeps_between_pages(db_engine, app_config, monkeypatch):
    """page_delay_seconds gates ``time.sleep`` between successive page fetches.

    Regression for the 2026-05-12 incident: walking multiple pages without a
    delay tripped arXiv's HTTP 429 rate-limit. The first page must not sleep;
    every subsequent page must.
    """
    feed_text = Path("tests/fixtures/arxiv_feed.xml").read_text(encoding="utf-8")
    empty_feed = (
        '<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["start"])
        if start == 0:
            return httpx.Response(200, text=feed_text)
        return httpx.Response(200, text=empty_feed)

    sleeps: list[float] = []
    monkeypatch.setattr("radar.collectors.arxiv.time.sleep", lambda s: sleeps.append(s))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source_config = app_config.sources.sources[0]
    with session_scope(db_engine) as session:
        source = session.scalar(select(Source).where(Source.key == source_config.id))
        fetch_and_store_arxiv(
            session,
            source,
            source_config,
            days=30,
            max_results=2,
            max_pages=5,
            page_delay_seconds=3.0,
            client=client,
            now=datetime(2026, 5, 11, 0, 0, tzinfo=UTC),
        )
    # Two pages were fetched → exactly one inter-page sleep, no sleep before page 0.
    assert sleeps == [3.0]


def test_store_normalized_item_dedupes_by_normalized_title(db_engine, app_config):
    source_config = app_config.sources.sources[0]
    item = NormalizedItem(
        type=ItemType.PAPER,
        title="Camera   Calibration: A Practical Method",
        abstract_or_summary="Calibration target detection.",
        url="https://example.test/a",
        published_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
        source_name=source_config.name,
        authors=[],
    )

    with session_scope(db_engine) as session:
        source = session.scalar(select(Source).where(Source.key == source_config.id))
        assert store_normalized_item(
            session=session, source=source, normalized=item, raw_payload={}
        )
        duplicate = item.model_copy(update={"url": "https://example.test/b"})
        assert not store_normalized_item(
            session=session,
            source=source,
            normalized=duplicate,
            raw_payload={},
        )
        assert len(session.scalars(select(Item)).all()) == 1
