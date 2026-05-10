from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.models import Item, ItemClassification
from radar.utils import date_bounds


def collect_score_debug_rows(
    session: Session,
    target_date: date,
    *,
    limit: int,
    include_zero: bool = False,
) -> list[tuple[Item, ItemClassification]]:
    start, end = date_bounds(target_date)
    query = (
        select(Item, ItemClassification)
        .join(ItemClassification, ItemClassification.item_id == Item.id)
        .where(Item.published_at >= start, Item.published_at <= end)
        .order_by(ItemClassification.final_score.desc(), Item.title.asc())
        .limit(limit)
    )
    if not include_zero:
        query = query.where(ItemClassification.relevance_score > 0)
    return list(session.execute(query).all())
