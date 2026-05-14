from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from radar.api.deps import get_session
from radar.api.schemas import TimelineResponse
from radar.reports.timeline import collect_timeline

router = APIRouter(tags=["timeline"])


@router.get("/timeline", response_model=TimelineResponse)
def get_timeline(
    session: Annotated[Session, Depends(get_session)],
    weeks: Annotated[int, Query(ge=1, le=52)] = 12,
) -> TimelineResponse:
    return collect_timeline(session, weeks=weeks)
