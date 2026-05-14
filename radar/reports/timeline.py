"""Timeline aggregation — first-decision-per-item, bucketed by ISO week.

Extracted from `radar/api/routes/timeline.py` so the same aggregation feeds
both the live API and the static bundle writer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.api.schemas import TimelineResponse, TimelineWeekOut
from radar.models import Item, RadarDecision
from radar.utils import utc_now


def _iso_week_key(moment: datetime) -> tuple[int, int]:
    iso = moment.isocalendar()
    return iso.year, iso.week


def _iso_week_label(year: int, week: int) -> tuple[str, str]:
    return f"{year}-W{week:02d}", f"W{week:02d}"


def collect_timeline(
    session: Session,
    *,
    weeks: int = 12,
    now: datetime | None = None,
) -> TimelineResponse:
    """Per-ISO-week counts of items by the ring of their FIRST decision.

    Anchors on the ISO week containing ``now`` (or ``utc_now()``) and walks
    back ``weeks`` Mondays.
    """
    if weeks < 1:
        msg = "weeks must be >= 1"
        raise ValueError(msg)

    moment = now or utc_now()
    today = moment.date()
    monday = datetime(today.year, today.month, today.day, tzinfo=UTC) - timedelta(
        days=today.weekday()
    )
    earliest_monday = monday - timedelta(weeks=weeks - 1)

    first_decisions = list(
        session.execute(
            select(RadarDecision.ring, Item.first_decided_at)
            .join(Item, RadarDecision.item_id == Item.id)
            .where(
                Item.first_decided_at.is_not(None),
                Item.first_decided_at >= earliest_monday,
                RadarDecision.previous_ring.is_(None),  # FIRST decision per item
            )
        ).all()
    )

    week_iter: list[tuple[int, int, datetime]] = []
    cursor = earliest_monday
    for _ in range(weeks):
        wkey = _iso_week_key(cursor)
        week_iter.append((wkey[0], wkey[1], cursor))
        cursor += timedelta(weeks=1)

    buckets: dict[tuple[int, int], dict[str, int]] = {
        (y, w): {"Use": 0, "Prototype": 0, "Evaluate": 0, "Watch": 0, "Ignore": 0}
        for y, w, _ in week_iter
    }

    for ring, decided_at in first_decisions:
        if decided_at is None:
            continue
        # Normalise: SQLite drops tzinfo on read.
        if decided_at.tzinfo is None:
            decided_at = decided_at.replace(tzinfo=UTC)
        key = _iso_week_key(decided_at)
        if key in buckets and ring in buckets[key]:
            buckets[key][ring] += 1

    rows: list[TimelineWeekOut] = []
    for year, week, _ in week_iter:
        iso, label = _iso_week_label(year, week)
        counts = buckets[(year, week)]
        rows.append(
            TimelineWeekOut(
                iso=iso,
                label=label,
                Use=counts["Use"],
                Prototype=counts["Prototype"],
                Evaluate=counts["Evaluate"],
                Watch=counts["Watch"],
                Ignore=counts["Ignore"],
            )
        )
    return TimelineResponse(weeks=rows)
