from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.enrichers.ollama import OllamaEmbeddingClient
from radar.models import Item, ItemEmbedding
from radar.schemas import EmbeddingsSettings
from radar.utils import date_bounds, date_window_bounds

EmbedOutcome = Literal["embedded", "skipped"]
EmbedProgressCallback = Callable[[int, int, Item, EmbedOutcome], None]


@dataclass(frozen=True)
class EmbedSummary:
    total: int
    embedded: int
    skipped: int


@dataclass(frozen=True)
class NearDuplicatePair:
    item_a_id: int
    item_a_title: str
    item_a_external_id: str | None
    item_b_id: int
    item_b_title: str
    item_b_external_id: str | None
    cosine: float


def build_embedding_text(item: Item) -> str:
    title = (item.title or "").strip()
    abstract = (item.abstract_or_summary or "").strip()
    if abstract:
        return f"{title}\n\n{abstract}"
    return title


def embed_items_for_date(
    session: Session,
    settings: EmbeddingsSettings,
    target_date: date,
    *,
    client: OllamaEmbeddingClient | None = None,
    on_progress: EmbedProgressCallback | None = None,
) -> EmbedSummary:
    start, end = date_bounds(target_date)
    items = list(
        session.scalars(select(Item).where(Item.published_at >= start, Item.published_at <= end))
    )
    return _embed_items(session, items, settings, client=client, on_progress=on_progress)


def _embed_items(
    session: Session,
    items: Sequence[Item],
    settings: EmbeddingsSettings,
    *,
    client: OllamaEmbeddingClient | None,
    on_progress: EmbedProgressCallback | None = None,
) -> EmbedSummary:
    if client is None:
        client = OllamaEmbeddingClient(
            model=settings.model,
            base_url=settings.base_url,
            timeout_seconds=settings.timeout_seconds,
        )
    embedded = 0
    skipped = 0
    total = len(items)
    for index, item in enumerate(items, start=1):
        existing = session.scalar(
            select(ItemEmbedding).where(
                ItemEmbedding.item_id == item.id,
                ItemEmbedding.model == settings.model,
            )
        )
        if existing is not None:
            skipped += 1
            if on_progress is not None:
                on_progress(index, total, item, "skipped")
            continue
        vector = client.embed(build_embedding_text(item))
        session.add(ItemEmbedding(item_id=item.id, model=settings.model, vector_json=vector))
        embedded += 1
        if on_progress is not None:
            on_progress(index, total, item, "embedded")
    session.flush()
    return EmbedSummary(total=total, embedded=embedded, skipped=skipped)


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def find_near_duplicates(
    session: Session,
    target_date: date,
    *,
    days: int,
    threshold: float,
    model: str,
) -> list[NearDuplicatePair]:
    start, end = date_window_bounds(target_date, days)
    rows = list(
        session.execute(
            select(Item, ItemEmbedding)
            .join(ItemEmbedding, ItemEmbedding.item_id == Item.id)
            .where(Item.published_at >= start, Item.published_at <= end)
            .where(ItemEmbedding.model == model)
            .order_by(Item.published_at.asc())
        ).all()
    )
    pairs: list[NearDuplicatePair] = []
    for i in range(len(rows)):
        item_a, emb_a = rows[i]
        for j in range(i + 1, len(rows)):
            item_b, emb_b = rows[j]
            similarity = cosine_similarity(emb_a.vector_json, emb_b.vector_json)
            if similarity >= threshold:
                pairs.append(
                    NearDuplicatePair(
                        item_a_id=item_a.id,
                        item_a_title=item_a.title,
                        item_a_external_id=item_a.external_id,
                        item_b_id=item_b.id,
                        item_b_title=item_b.title,
                        item_b_external_id=item_b.external_id,
                        cosine=round(similarity, 4),
                    )
                )
    pairs.sort(key=lambda pair: pair.cosine, reverse=True)
    return pairs
