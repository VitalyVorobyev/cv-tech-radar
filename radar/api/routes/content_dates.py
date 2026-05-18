"""Content-date API — which days have a candidate queue or a digest.

Backs the date-grid landing of the Queue and Digest views: the frontend asks
once for every non-empty day rather than probing dates blind.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from radar.api.deps import get_session
from radar.api.schemas import ContentDatesResponse, DigestDateOut, QueueDateOut
from radar.reports.content_dates import collect_content_dates

router = APIRouter(tags=["content-dates"])


@router.get("/content-dates", response_model=ContentDatesResponse)
def get_content_dates(
    session: Annotated[Session, Depends(get_session)],
) -> ContentDatesResponse:
    dates = collect_content_dates(session)
    return ContentDatesResponse(
        queue=[
            QueueDateOut(
                date=entry.date,
                candidate_count=entry.candidate_count,
                decided_count=entry.decided_count,
            )
            for entry in dates.queue
        ],
        digest=[
            DigestDateOut(date=entry.date, title=entry.title, item_count=entry.item_count)
            for entry in dates.digest
        ],
    )
