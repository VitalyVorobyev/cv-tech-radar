from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from radar.api.deps import get_session
from radar.api.schemas import BoardResponse, BoardRingsOut, DigestItemOut
from radar.models import Item, RadarDecision
from radar.reports.digest import collect_digest_rows
from radar.schemas import RadarRing
from radar.utils import parse_date_arg

router = APIRouter(tags=["board"])


def _to_item_out(item: Item, decision: RadarDecision) -> DigestItemOut:
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


@router.get("/board", response_model=BoardResponse)
def get_board(
    session: Annotated[Session, Depends(get_session)],
    date: Annotated[str, Query()] = "today",
    days: Annotated[int, Query(ge=1)] = 7,
) -> BoardResponse:
    try:
        target_date = parse_date_arg(date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid date: {exc}") from exc

    rows = collect_digest_rows(session, target_date, days)
    rings: dict[str, list[DigestItemOut]] = {ring.value: [] for ring in RadarRing}
    for item, decision in rows:
        rings.setdefault(decision.ring, []).append(_to_item_out(item, decision))

    return BoardResponse(
        rings=BoardRingsOut(
            Use=rings.get(RadarRing.USE.value, []),
            Prototype=rings.get(RadarRing.PROTOTYPE.value, []),
            Evaluate=rings.get(RadarRing.EVALUATE.value, []),
            Watch=rings.get(RadarRing.WATCH.value, []),
            Ignore=rings.get(RadarRing.IGNORE.value, []),
        )
    )
