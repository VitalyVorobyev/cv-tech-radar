from __future__ import annotations

from collections import OrderedDict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from radar.api.deps import get_session
from radar.api.schemas import DigestItemOut, DigestResponse, DigestSectionsOut
from radar.models import Item, RadarDecision
from radar.reports.digest import collect_digest_rows
from radar.schemas import RadarRing
from radar.utils import parse_date_arg

router = APIRouter(tags=["digest"])


def _to_digest_item(item: Item, decision: RadarDecision) -> DigestItemOut:
    return DigestItemOut(
        item_id=item.id,
        title=item.title,
        url=item.url,
        tracks=decision.tracks_json or [],
        reason=decision.decision_reason,
        action=decision.action,
        uncertain=bool(decision.uncertain),
        ring=decision.ring,
        decided_by=decision.decided_by,
        created_at=decision.created_at,
    )


@router.get("/digest", response_model=DigestResponse)
def get_digest(
    session: Annotated[Session, Depends(get_session)],
    date: Annotated[str, Query()] = "today",
    days: Annotated[int, Query(ge=1)] = 1,
) -> DigestResponse:
    try:
        target_date = parse_date_arg(date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid date: {exc}") from exc

    rows = collect_digest_rows(session, target_date, days)

    by_ring: OrderedDict[str, list[DigestItemOut]] = OrderedDict(
        (ring.value, []) for ring in RadarRing
    )
    uncertainty: list[DigestItemOut] = []
    for item, decision in rows:
        entry = _to_digest_item(item, decision)
        by_ring.setdefault(decision.ring, []).append(entry)
        if decision.uncertain:
            uncertainty.append(entry)

    sections = DigestSectionsOut(
        Use=by_ring.get(RadarRing.USE.value, []),
        Prototype=by_ring.get(RadarRing.PROTOTYPE.value, []),
        Evaluate=by_ring.get(RadarRing.EVALUATE.value, []),
        Watch=by_ring.get(RadarRing.WATCH.value, []),
        Ignore=by_ring.get(RadarRing.IGNORE.value, []),
        Uncertainty=uncertainty,
    )
    return DigestResponse(date=target_date.isoformat(), days=days, sections=sections)
