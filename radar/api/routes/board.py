from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from radar.api.deps import get_session
from radar.api.movement import classify_movement
from radar.api.routes.queue import latest_llm_judgments
from radar.api.schemas import (
    BoardCountsOut,
    BoardItemOut,
    BoardResponse,
    BoardRingsOut,
    LLMJudgmentOut,
)
from radar.decisions import latest_confirmed_decision_subq
from radar.models import Item, RadarDecision
from radar.reports.digest import collect_board_rows
from radar.schemas import RadarRing
from radar.utils import utc_now

router = APIRouter(tags=["board"])


def _to_item_out(
    item: Item,
    decision: RadarDecision,
    score: float | None,
    llm_judgment: LLMJudgmentOut | None,
    now: datetime,
) -> BoardItemOut:
    movement = classify_movement(
        current_ring=decision.ring,
        previous_ring=decision.previous_ring,
        decided_at=decision.created_at,
        first_decided_at=item.first_decided_at,
        now=now,
    )
    return BoardItemOut(
        item_id=item.id,
        title=item.title,
        url=item.url,
        tracks=decision.tracks_json or [],
        reason=decision.decision_reason,
        action=decision.action,
        uncertain=bool(decision.uncertain),
        ring=decision.ring,
        decided_by=decision.decided_by,
        decided_at=decision.created_at,
        score=score,
        llm_judgment=llm_judgment,
        movement=movement,
    )


@router.get("/board", response_model=BoardResponse)
def get_board(
    session: Annotated[Session, Depends(get_session)],
    decided_since: Annotated[datetime | None, Query()] = None,
    include_ignore: Annotated[bool, Query()] = False,
) -> BoardResponse:
    try:
        rows = collect_board_rows(
            session,
            decided_since=decided_since,
            include_ignore=include_ignore,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    judgments = latest_llm_judgments(session, [item.id for item, _, _ in rows])
    now = utc_now()
    rings: dict[str, list[BoardItemOut]] = {ring.value: [] for ring in RadarRing}
    for item, decision, score in rows:
        rings.setdefault(decision.ring, []).append(
            _to_item_out(item, decision, score, judgments.get(item.id), now)
        )

    counts = _count_all_rings(session, decided_since=decided_since)

    return BoardResponse(
        rings=BoardRingsOut(
            Use=rings.get(RadarRing.USE.value, []),
            Prototype=rings.get(RadarRing.PROTOTYPE.value, []),
            Evaluate=rings.get(RadarRing.EVALUATE.value, []),
            Watch=rings.get(RadarRing.WATCH.value, []),
            Ignore=rings.get(RadarRing.IGNORE.value, []),
        ),
        counts=counts,
        decided_since=decided_since,
        include_ignore=include_ignore,
    )


def _count_all_rings(
    session: Session,
    *,
    decided_since: datetime | None,
) -> BoardCountsOut:
    """Return per-ring counts of latest confirmed decisions (Ignore included).

    Shares the gate with `collect_board_rows` so the counts match the deduped
    `rings` payload — unconfirmed proposals are counted by neither.
    """
    latest_decision_id_subq = latest_confirmed_decision_subq().subquery()
    stmt = (
        select(RadarDecision.ring, func.count())
        .join(
            latest_decision_id_subq,
            RadarDecision.id == latest_decision_id_subq.c.decision_id,
        )
        .group_by(RadarDecision.ring)
    )
    if decided_since is not None:
        stmt = stmt.where(RadarDecision.created_at >= decided_since)
    counts: dict[str, int] = dict(session.execute(stmt).all())
    return BoardCountsOut(
        Use=counts.get(RadarRing.USE.value, 0),
        Prototype=counts.get(RadarRing.PROTOTYPE.value, 0),
        Evaluate=counts.get(RadarRing.EVALUATE.value, 0),
        Watch=counts.get(RadarRing.WATCH.value, 0),
        Ignore=counts.get(RadarRing.IGNORE.value, 0),
    )
