from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import select

from radar.db import session_scope
from radar.embeddings import (
    build_embedding_text,
    cosine_similarity,
    embed_items_for_date,
    find_near_duplicates,
)
from radar.enrichers.ollama import OllamaEmbeddingClient
from radar.models import Item, ItemEmbedding
from radar.schemas import EmbeddingsSettings


def _settings(model: str = "test-embed:latest") -> EmbeddingsSettings:
    return EmbeddingsSettings(
        enabled=True,
        provider="ollama",
        model=model,
        base_url="http://ollama.test",
        timeout_seconds=5,
        near_duplicate_threshold=0.9,
    )


def _make_item(
    session,
    *,
    external_id: str,
    title: str,
    abstract: str = "",
    published: datetime,
) -> Item:
    item = Item(
        type="paper",
        title=title,
        normalized_title=title.casefold(),
        abstract_or_summary=abstract,
        url=f"https://example.test/{external_id}",
        pdf_url=None,
        published_at=published,
        updated_at=None,
        source_name="arXiv cs.CV",
        external_id=external_id,
        arxiv_id=external_id,
        authors_json=[],
        organizations_json=[],
        metadata_json={},
    )
    session.add(item)
    session.flush()
    return item


def _mock_client(
    vectors_by_text: dict[str, list[float]],
    *,
    model: str = "test-embed:latest",
) -> OllamaEmbeddingClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embeddings"
        import json

        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == model
        prompt = payload["prompt"]
        if prompt not in vectors_by_text:
            return httpx.Response(500, json={"error": f"no fixture vector for: {prompt!r}"})
        return httpx.Response(200, json={"embedding": vectors_by_text[prompt]})

    return OllamaEmbeddingClient(
        model=model,
        base_url="http://ollama.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_cosine_similarity_orthogonal_returns_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_identical_returns_one():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_similarity_scale_invariant():
    assert cosine_similarity([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == pytest.approx(1.0)


def test_cosine_similarity_handles_zero_and_empty_vectors():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0  # length mismatch


def test_build_embedding_text_concatenates_title_and_abstract(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    with session_scope(db_engine) as session:
        item = _make_item(
            session,
            external_id="x",
            title="Camera Calibration",
            abstract="A study of bundle adjustment.",
            published=pub,
        )
        assert build_embedding_text(item) == ("Camera Calibration\n\nA study of bundle adjustment.")


def test_build_embedding_text_falls_back_to_title_only(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    with session_scope(db_engine) as session:
        item = _make_item(
            session,
            external_id="y",
            title="Title only",
            abstract="",
            published=pub,
        )
        assert build_embedding_text(item) == "Title only"


def test_embed_items_for_date_stores_vectors_and_is_idempotent(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    settings = _settings()
    with session_scope(db_engine) as session:
        _make_item(
            session,
            external_id="a",
            title="A",
            abstract="alpha",
            published=pub,
        )
        _make_item(
            session,
            external_id="b",
            title="B",
            abstract="beta",
            published=pub,
        )
        client = _mock_client({"A\n\nalpha": [1.0, 0.0, 0.0], "B\n\nbeta": [0.0, 1.0, 0.0]})
        first = embed_items_for_date(session, settings, date(2026, 5, 10), client=client)
        assert first.total == 2 and first.embedded == 2 and first.skipped == 0

        stored = session.scalars(select(ItemEmbedding)).all()
        assert len(stored) == 2
        assert {tuple(emb.vector_json) for emb in stored} == {
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
        }

        # Second run with no new items must skip, not re-call the client.
        empty_client = _mock_client({})  # would 500 on any call
        second = embed_items_for_date(session, settings, date(2026, 5, 10), client=empty_client)
        assert second.total == 2 and second.embedded == 0 and second.skipped == 2


def test_embed_items_for_date_separates_by_model(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    with session_scope(db_engine) as session:
        _make_item(
            session,
            external_id="a",
            title="A",
            abstract="alpha",
            published=pub,
        )
        client_v1 = _mock_client({"A\n\nalpha": [1.0, 0.0]}, model="model-v1")
        client_v2 = _mock_client({"A\n\nalpha": [0.0, 1.0]}, model="model-v2")
        first = embed_items_for_date(
            session,
            _settings(model="model-v1"),
            date(2026, 5, 10),
            client=client_v1,
        )
        assert first.embedded == 1
        second = embed_items_for_date(
            session,
            _settings(model="model-v2"),
            date(2026, 5, 10),
            client=client_v2,
        )
        assert second.embedded == 1  # not skipped — different model

        rows = session.scalars(select(ItemEmbedding)).all()
        assert {row.model for row in rows} == {"model-v1", "model-v2"}


def test_find_near_duplicates_filters_by_threshold_and_model(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    with session_scope(db_engine) as session:
        a = _make_item(session, external_id="a", title="A", published=pub)
        b = _make_item(session, external_id="b", title="B", published=pub)
        c = _make_item(session, external_id="c", title="C", published=pub)
        # a and b are identical; c is orthogonal.
        session.add(ItemEmbedding(item_id=a.id, model="m", vector_json=[1.0, 0.0]))
        session.add(ItemEmbedding(item_id=b.id, model="m", vector_json=[1.0, 0.0]))
        session.add(ItemEmbedding(item_id=c.id, model="m", vector_json=[0.0, 1.0]))
        # Wrong model — must not appear in results.
        session.add(ItemEmbedding(item_id=a.id, model="other", vector_json=[1.0, 0.0]))
        session.add(ItemEmbedding(item_id=c.id, model="other", vector_json=[1.0, 0.0]))
        session.flush()

        pairs = find_near_duplicates(
            session,
            date(2026, 5, 10),
            days=1,
            threshold=0.9,
            model="m",
        )

    assert len(pairs) == 1
    assert pairs[0].item_a_external_id == "a"
    assert pairs[0].item_b_external_id == "b"
    assert pairs[0].cosine == pytest.approx(1.0)


def test_find_near_duplicates_respects_date_window(db_engine):
    older = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)
    recent = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    with session_scope(db_engine) as session:
        old_item = _make_item(session, external_id="old", title="Old", published=older)
        new_item = _make_item(session, external_id="new", title="New", published=recent)
        session.add(ItemEmbedding(item_id=old_item.id, model="m", vector_json=[1.0, 0.0]))
        session.add(ItemEmbedding(item_id=new_item.id, model="m", vector_json=[1.0, 0.0]))
        session.flush()

        pairs = find_near_duplicates(
            session,
            date(2026, 5, 10),
            days=14,
            threshold=0.9,
            model="m",
        )

    # Old item is outside the 14-day window; no pair surfaces.
    assert pairs == []


def test_embed_items_for_date_invokes_on_progress(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    events: list[tuple[int, int, str, str]] = []

    def cb(index: int, total: int, item, outcome: str) -> None:
        events.append((index, total, item.external_id, outcome))

    with session_scope(db_engine) as session:
        _make_item(session, external_id="a", title="A", abstract="alpha", published=pub)
        _make_item(session, external_id="b", title="B", abstract="beta", published=pub)
        client = _mock_client({"A\n\nalpha": [1.0, 0.0], "B\n\nbeta": [0.0, 1.0]})
        embed_items_for_date(
            session,
            _settings(),
            date(2026, 5, 10),
            client=client,
            on_progress=cb,
        )
        # Re-run; everything should now hit the skipped branch.
        events.clear()
        empty_client = _mock_client({})
        embed_items_for_date(
            session,
            _settings(),
            date(2026, 5, 10),
            client=empty_client,
            on_progress=cb,
        )

    assert [e[3] for e in events] == ["skipped", "skipped"]
    assert [e[0] for e in events] == [1, 2]
    assert {e[1] for e in events} == {2}


def test_find_near_duplicates_sorted_descending_by_cosine(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    with session_scope(db_engine) as session:
        a = _make_item(session, external_id="a", title="A", published=pub)
        b = _make_item(session, external_id="b", title="B", published=pub)
        c = _make_item(session, external_id="c", title="C", published=pub)
        d = _make_item(session, external_id="d", title="D", published=pub)
        session.add(ItemEmbedding(item_id=a.id, model="m", vector_json=[1.0, 0.0]))
        session.add(ItemEmbedding(item_id=b.id, model="m", vector_json=[1.0, 0.0]))
        session.add(ItemEmbedding(item_id=c.id, model="m", vector_json=[0.95, 0.31]))
        session.add(ItemEmbedding(item_id=d.id, model="m", vector_json=[0.95, 0.31]))
        session.flush()

        pairs = find_near_duplicates(
            session,
            date(2026, 5, 10),
            days=1,
            threshold=0.5,
            model="m",
        )

    cosines = [pair.cosine for pair in pairs]
    assert cosines == sorted(cosines, reverse=True)
    assert pairs[0].cosine == pytest.approx(1.0)
