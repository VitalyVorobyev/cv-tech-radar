"""Content-date listings — which days actually have a candidate queue or digest.

Backs the date-grid landing of the Queue and Digest views: instead of picking a
date blind from a calendar input, the UI shows one card per non-empty day. Pure
SQLAlchemy read helpers, no ``AppConfig`` dependency — same style as
:mod:`radar.reports.digest`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from radar.models import Digest, Item, ItemClassification, RadarDecision


@dataclass(frozen=True)
class QueueDateEntry:
    """One day that has a candidate queue."""

    date: str  # ISO date (UTC day of ``Item.published_at``)
    candidate_count: int  # classified items published that day
    decided_count: int  # of those, items with at least one curator decision


@dataclass(frozen=True)
class DigestDateEntry:
    """One day that has a published digest."""

    date: str  # ISO date — the ``digests`` row's date key
    title: str
    item_count: int  # decisions recorded for items published that day (1-day proxy)


@dataclass(frozen=True)
class ContentDates:
    queue: list[QueueDateEntry] = field(default_factory=list)
    digest: list[DigestDateEntry] = field(default_factory=list)


def _decided_counts_by_day(session: Session) -> dict[str, int]:
    """Map UTC published-day -> count of distinct items with >=1 decision."""
    day = func.date(Item.published_at)
    rows = session.execute(
        select(day.label("day"), func.count(func.distinct(Item.id)).label("n"))
        .join(RadarDecision, RadarDecision.item_id == Item.id)
        .group_by(day)
    ).all()
    return {row.day: row.n for row in rows if row.day is not None}


def _collect_queue_dates(session: Session) -> list[QueueDateEntry]:
    """Days with classified items, newest first — the queue is non-empty there."""
    day = func.date(Item.published_at)
    classified = session.execute(
        select(day.label("day"), func.count(func.distinct(Item.id)).label("n"))
        .join(ItemClassification, ItemClassification.item_id == Item.id)
        .group_by(day)
    ).all()
    decided = _decided_counts_by_day(session)
    entries = [
        QueueDateEntry(
            date=row.day,
            candidate_count=row.n,
            decided_count=decided.get(row.day, 0),
        )
        for row in classified
        if row.day is not None
    ]
    entries.sort(key=lambda entry: entry.date, reverse=True)
    return entries


def _collect_digest_dates(session: Session) -> list[DigestDateEntry]:
    """Days with a published daily digest, newest first."""
    digests = session.scalars(
        select(Digest).where(Digest.kind == "daily").order_by(Digest.date.desc())
    ).all()
    decided = _decided_counts_by_day(session)
    return [
        DigestDateEntry(
            date=digest.date,
            title=digest.title,
            item_count=decided.get(digest.date, 0),
        )
        for digest in digests
    ]


def collect_content_dates(session: Session) -> ContentDates:
    """Return the non-empty queue days and digest days, each newest-first."""
    return ContentDates(
        queue=_collect_queue_dates(session),
        digest=_collect_digest_dates(session),
    )


__all__ = [
    "ContentDates",
    "DigestDateEntry",
    "QueueDateEntry",
    "collect_content_dates",
]
