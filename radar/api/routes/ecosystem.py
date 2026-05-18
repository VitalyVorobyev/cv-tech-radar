"""Ecosystem radar API — artifact board, release-event feed, and decisions.

Mirrors the papers radar routes (``board`` / ``digest`` / ``items`` /
``decisions``) but reads the ``artifact_*`` tables. The board groups artifacts
by their resolved ring (latest decision, else a status-derived seed ring); the
events endpoint windows release events; the decision POST records a curator
ring exactly like the papers radar.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from radar.api.deps import get_session
from radar.api.movement import classify_movement
from radar.api.schemas import (
    ArtifactBoardItem,
    ArtifactDecisionCreate,
    ArtifactDecisionCreatedOut,
    ArtifactDecisionEntry,
    ArtifactDetailResponse,
    ArtifactRefDetail,
    BoardCountsOut,
    EcosystemBoardResponse,
    EcosystemBoardRingsOut,
    EcosystemEventItem,
    EcosystemEventsResponse,
    EcosystemLatestEvent,
)
from radar.artifact_decisions import record_artifact_decision
from radar.decisions import DecisionError
from radar.models import Artifact, ArtifactEvent, ArtifactRef
from radar.reports.ecosystem import (
    EcosystemBoardRow,
    collect_ecosystem_board_rows,
    collect_ecosystem_events,
    seed_ring,
)
from radar.schemas import RadarRing
from radar.utils import parse_date_arg, utc_now

router = APIRouter(tags=["ecosystem"])


def _to_event_item(
    event: ArtifactEvent, artifact: Artifact, ref: ArtifactRef | None
) -> EcosystemEventItem:
    return EcosystemEventItem(
        id=event.id,
        artifact_id=artifact.id,
        artifact_key=artifact.key,
        artifact_name=artifact.name,
        ecosystem=ref.ecosystem if ref is not None else "unknown",
        event_type=event.event_type,
        version=event.version,
        event_date=event.event_date,
        summary=event.summary,
        body=event.body,
        url=event.url,
        severity=event.severity,
        relevant=bool(event.relevant),
        matched_keywords=event.matched_keywords_json or [],
    )


def _to_board_item(row: EcosystemBoardRow, now: datetime) -> ArtifactBoardItem:
    artifact = row.artifact
    movement = None
    if row.decided_at is not None:
        movement = classify_movement(
            current_ring=row.ring,
            previous_ring=row.previous_ring,
            decided_at=row.decided_at,
            first_decided_at=artifact.first_decided_at,
            now=now,
        )
    latest_event = None
    if row.latest_event is not None:
        event = row.latest_event
        latest_event = EcosystemLatestEvent(
            event_type=event.event_type,
            version=event.version,
            event_date=event.event_date,
            summary=event.summary,
            url=event.url,
        )
    return ArtifactBoardItem(
        artifact_id=artifact.id,
        key=artifact.key,
        name=artifact.name,
        description=artifact.description,
        status=artifact.status,
        ring=row.ring,
        capability=artifact.capability,
        tracks=artifact.tracks_json or [],
        ecosystems=row.ecosystems,
        latest_event=latest_event,
        recent_event_count=row.recent_event_count,
        decided_at=row.decided_at,
        movement=movement,
    )


@router.get("/ecosystem/board", response_model=EcosystemBoardResponse)
def get_ecosystem_board(
    session: Annotated[Session, Depends(get_session)],
    include_ignore: Annotated[bool, Query()] = False,
) -> EcosystemBoardResponse:
    # Fetch every artifact (including Ignore) so `counts` is complete; the
    # rendered `rings` then hide Ignore unless it is explicitly requested.
    rows = collect_ecosystem_board_rows(session, include_ignore=True)
    now = utc_now()
    rings: dict[str, list[ArtifactBoardItem]] = {ring.value: [] for ring in RadarRing}
    counts: dict[str, int] = {ring.value: 0 for ring in RadarRing}
    for row in rows:
        counts[row.ring] = counts.get(row.ring, 0) + 1
        if row.ring == RadarRing.IGNORE.value and not include_ignore:
            continue
        rings.setdefault(row.ring, []).append(_to_board_item(row, now))

    return EcosystemBoardResponse(
        rings=EcosystemBoardRingsOut(
            Use=rings.get(RadarRing.USE.value, []),
            Prototype=rings.get(RadarRing.PROTOTYPE.value, []),
            Evaluate=rings.get(RadarRing.EVALUATE.value, []),
            Watch=rings.get(RadarRing.WATCH.value, []),
            Ignore=rings.get(RadarRing.IGNORE.value, []),
        ),
        counts=BoardCountsOut(
            Use=counts.get(RadarRing.USE.value, 0),
            Prototype=counts.get(RadarRing.PROTOTYPE.value, 0),
            Evaluate=counts.get(RadarRing.EVALUATE.value, 0),
            Watch=counts.get(RadarRing.WATCH.value, 0),
            Ignore=counts.get(RadarRing.IGNORE.value, 0),
        ),
        include_ignore=include_ignore,
    )


@router.get("/ecosystem/events", response_model=EcosystemEventsResponse)
def get_ecosystem_events(
    session: Annotated[Session, Depends(get_session)],
    date: Annotated[str, Query()] = "today",
    days: Annotated[int, Query(ge=1)] = 7,
    relevant_only: Annotated[bool, Query()] = True,
    artifact_key: Annotated[str | None, Query()] = None,
    ecosystem: Annotated[str | None, Query()] = None,
) -> EcosystemEventsResponse:
    try:
        target_date = parse_date_arg(date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid date: {exc}") from exc

    rows = collect_ecosystem_events(
        session,
        target_date=target_date,
        days=days,
        relevant_only=relevant_only,
        artifact_key=artifact_key,
        ecosystem=ecosystem,
    )
    events = [_to_event_item(event, artifact, ref) for event, artifact, ref in rows]
    return EcosystemEventsResponse(date=target_date.isoformat(), days=days, events=events)


@router.get("/ecosystem/artifacts/{artifact_id}", response_model=ArtifactDetailResponse)
def get_ecosystem_artifact(
    session: Annotated[Session, Depends(get_session)],
    artifact_id: Annotated[int, Path(ge=1)],
) -> ArtifactDetailResponse:
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"artifact {artifact_id} not found")

    refs = sorted(artifact.refs, key=lambda ref: ref.ecosystem)
    ref_details = [
        ArtifactRefDetail(
            ecosystem=ref.ecosystem,
            ref=ref.ref,
            last_version=ref.state.last_version if ref.state else None,
            last_release_at=ref.state.last_release_at if ref.state else None,
            last_status=ref.state.last_status if ref.state else "unknown",
            last_checked_at=ref.state.last_checked_at if ref.state else None,
        )
        for ref in refs
    ]

    refs_by_id = {ref.id: ref for ref in artifact.refs}
    events_sorted = sorted(
        artifact.events, key=lambda event: (event.event_date, event.id), reverse=True
    )
    events = [
        _to_event_item(event, artifact, refs_by_id.get(event.artifact_ref_id))
        for event in events_sorted
    ]

    decisions_sorted = sorted(
        artifact.decisions, key=lambda decision: (decision.created_at, decision.id)
    )
    decisions = [
        ArtifactDecisionEntry(
            ring=decision.ring,
            tracks=decision.tracks_json or [],
            reason=decision.decision_reason,
            action=decision.action,
            decided_by=decision.decided_by,
            uncertain=bool(decision.uncertain),
            decided_at=decision.created_at,
        )
        for decision in decisions_sorted
    ]
    ring = decisions_sorted[-1].ring if decisions_sorted else seed_ring(artifact.status)

    return ArtifactDetailResponse(
        artifact_id=artifact.id,
        key=artifact.key,
        name=artifact.name,
        description=artifact.description,
        status=artifact.status,
        capability=artifact.capability,
        homepage_url=artifact.homepage_url,
        ring=ring,
        tracks=artifact.tracks_json or [],
        refs=ref_details,
        events=events,
        decisions=decisions,
    )


@router.post(
    "/ecosystem/decisions",
    response_model=ArtifactDecisionCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
def create_ecosystem_decision(
    payload: ArtifactDecisionCreate,
    session: Annotated[Session, Depends(get_session)],
) -> ArtifactDecisionCreatedOut:
    try:
        decision = record_artifact_decision(
            session,
            artifact_id=payload.artifact_id,
            ring=payload.ring,
            tracks=payload.tracks,
            reason=payload.reason,
            action=payload.action,
            decided_by=payload.decided_by,
            uncertain=payload.uncertain,
        )
    except DecisionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    session.flush()
    return ArtifactDecisionCreatedOut(decision_id=decision.id, created_at=decision.created_at)
