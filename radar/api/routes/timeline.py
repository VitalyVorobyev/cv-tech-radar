from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.api.deps import get_session
from radar.api.schemas import TimelineResponse, TimelineWeekOut
from radar.models import Item, RadarDecision
from radar.utils import utc_now

router = APIRouter(tags=["timeline"])


def _iso_week_key(moment: datetime) -> tuple[int, int]:
    iso = moment.isocalendar()
    return iso.year, iso.week


def _iso_week_label(year: int, week: int) -> tuple[str, str]:
    return f"{year}-W{week:02d}", f"W{week:02d}"


@router.get("/timeline", response_model=TimelineResponse)
def get_timeline(
    session: Annotated[Session, Depends(get_session)],
    weeks: Annotated[int, Query(ge=1, le=52)] = 12,
) -> TimelineResponse:
    now = utc_now()
    # Anchor on the current ISO week's Monday (00:00 UTC).
    today = now.date()
    monday = datetime(today.year, today.month, today.day, tzinfo=UTC) - timedelta(
        days=today.weekday()
    )
    earliest_monday = monday - timedelta(weeks=weeks - 1)

    # For each item, find its FIRST decision and its latest ring (latest decision per item).
    # We want to bucket by first_decided_at and by the ring of that FIRST decision —
    # "items that landed in each ring per week".
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

    # Pre-seed weeks in chronological order.
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
