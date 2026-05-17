"""Pre-render the public radar state into static JSON files.

Produces the minimum payload a no-backend React build needs for the public
views (Radar board, Tracks, Timeline) plus per-item JSON for the side panel.
The output shapes mirror the FastAPI response models so the frontend can swap
data sources without a transformation layer.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.api.movement import classify_movement
from radar.api.schemas import (
    ArtifactBoardItem,
    ArtifactDecisionEntry,
    ArtifactDetailResponse,
    ArtifactRefDetail,
    BoardCountsOut,
    BoardItemOut,
    BoardResponse,
    BoardRingsOut,
    EcosystemBoardResponse,
    EcosystemBoardRingsOut,
    EcosystemEventItem,
    EcosystemEventsResponse,
    EcosystemLatestEvent,
    HistoryEntryOut,
    ItemDetailOut,
)
from radar.models import Artifact, ArtifactEvent, ArtifactRef, Item, RadarDecision
from radar.reports.digest import collect_board_rows
from radar.reports.ecosystem import (
    EcosystemBoardRow,
    collect_ecosystem_board_rows,
    collect_ecosystem_events,
    seed_ring,
)
from radar.reports.timeline import collect_timeline
from radar.schemas import AppConfig, RadarRing
from radar.utils import ensure_dir, utc_now

# The static events file ships a wide, unfiltered window so the frontend's
# "relevant only" toggle works client-side without a backend.
ECOSYSTEM_EVENTS_WINDOW_DAYS = 180

BUNDLE_FILES = (
    "board.json",
    "tracks.json",
    "timeline.json",
    "meta.json",
    "ecosystem-board.json",
    "ecosystem-events.json",
)


def _serialize_board(
    rows: list[tuple[Item, RadarDecision, float | None]], *, now: datetime
) -> BoardResponse:
    """Build a BoardResponse from collect_board_rows output (no LLM judgments)."""
    rings: dict[str, list[BoardItemOut]] = {ring.value: [] for ring in RadarRing}
    counts: dict[str, int] = {ring.value: 0 for ring in RadarRing}
    for item, decision, score in rows:
        movement = classify_movement(
            current_ring=decision.ring,
            previous_ring=decision.previous_ring,
            decided_at=decision.created_at,
            first_decided_at=item.first_decided_at,
            now=now,
        )
        rings.setdefault(decision.ring, []).append(
            BoardItemOut(
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
                llm_judgment=None,
                movement=movement,
            )
        )
        counts[decision.ring] = counts.get(decision.ring, 0) + 1
    return BoardResponse(
        rings=BoardRingsOut(
            Use=rings.get(RadarRing.USE.value, []),
            Prototype=rings.get(RadarRing.PROTOTYPE.value, []),
            Evaluate=rings.get(RadarRing.EVALUATE.value, []),
            Watch=rings.get(RadarRing.WATCH.value, []),
            Ignore=[],
        ),
        counts=BoardCountsOut(
            Use=counts.get(RadarRing.USE.value, 0),
            Prototype=counts.get(RadarRing.PROTOTYPE.value, 0),
            Evaluate=counts.get(RadarRing.EVALUATE.value, 0),
            Watch=counts.get(RadarRing.WATCH.value, 0),
            Ignore=0,
        ),
        decided_since=None,
        include_ignore=False,
    )


def _serialize_tracks(
    board: BoardResponse,
    config: AppConfig,
) -> dict:
    """`{ tracks: [{id, name, item_ids: [...]}] }` derived from board membership."""
    members: dict[str, list[int]] = {track.name: [] for track in config.topics.tracks}
    for ring in (board.rings.Use, board.rings.Prototype, board.rings.Evaluate, board.rings.Watch):
        for item in ring:
            for track in item.tracks:
                members.setdefault(track, []).append(item.item_id)
    return {
        "tracks": [
            {
                "id": track.id,
                "name": track.name,
                "quadrant": track.quadrant,
                "item_ids": members.get(track.name, []),
            }
            for track in config.topics.tracks
        ]
    }


def _serialize_item_detail(
    session: Session,
    item: Item,
    *,
    now: datetime,
) -> ItemDetailOut:
    """Mirror radar/api/routes/items.py:get_item but without the HTTP layer."""
    decisions = list(
        session.scalars(
            select(RadarDecision)
            .where(RadarDecision.item_id == item.id)
            .order_by(RadarDecision.created_at.asc(), RadarDecision.id.asc())
        )
    )
    history: list[HistoryEntryOut] = []
    last_ring: str | None = None
    for d in decisions:
        if d.ring != last_ring:
            history.append(HistoryEntryOut(ring=d.ring, at=d.created_at))
            last_ring = d.ring

    latest = decisions[-1] if decisions else None
    tracks = (latest.tracks_json or []) if latest else []
    movement = (
        classify_movement(
            current_ring=latest.ring,
            previous_ring=latest.previous_ring,
            decided_at=latest.created_at,
            first_decided_at=item.first_decided_at,
            now=now,
        )
        if latest
        else None
    )
    return ItemDetailOut(
        id=item.id,
        title=item.title,
        abstract=item.abstract_or_summary or "",
        url=item.url,
        ring=latest.ring if latest else "",
        track=tracks[0] if tracks else "",
        tracks=tracks,
        reason=latest.decision_reason if latest else "",
        uncertain=bool(latest.uncertain) if latest else False,
        source=item.source_name,
        published_at=item.published_at,
        decided_at=latest.created_at if latest else item.created_at,
        decided_by=(latest.decided_by or None) if latest else None,
        history=history,
        movement=movement,
    )


def _event_to_item(
    event: ArtifactEvent, artifact: Artifact, ref: ArtifactRef
) -> EcosystemEventItem:
    """Mirror radar/api/routes/ecosystem.py:_to_event_item without the HTTP layer."""
    return EcosystemEventItem(
        id=event.id,
        artifact_id=artifact.id,
        artifact_key=artifact.key,
        artifact_name=artifact.name,
        ecosystem=ref.ecosystem,
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


def _board_row_to_item(row: EcosystemBoardRow, *, now: datetime) -> ArtifactBoardItem:
    """Mirror radar/api/routes/ecosystem.py:_to_board_item without the HTTP layer."""
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


def _serialize_ecosystem_board(
    rows: list[EcosystemBoardRow], *, now: datetime
) -> EcosystemBoardResponse:
    """Build an EcosystemBoardResponse from board rows (Ignore excluded, like the API)."""
    rings: dict[str, list[ArtifactBoardItem]] = {ring.value: [] for ring in RadarRing}
    counts: dict[str, int] = {ring.value: 0 for ring in RadarRing}
    for row in rows:
        counts[row.ring] = counts.get(row.ring, 0) + 1
        if row.ring == RadarRing.IGNORE.value:
            continue
        rings.setdefault(row.ring, []).append(_board_row_to_item(row, now=now))
    return EcosystemBoardResponse(
        rings=EcosystemBoardRingsOut(
            Use=rings.get(RadarRing.USE.value, []),
            Prototype=rings.get(RadarRing.PROTOTYPE.value, []),
            Evaluate=rings.get(RadarRing.EVALUATE.value, []),
            Watch=rings.get(RadarRing.WATCH.value, []),
            Ignore=[],
        ),
        counts=BoardCountsOut(
            Use=counts.get(RadarRing.USE.value, 0),
            Prototype=counts.get(RadarRing.PROTOTYPE.value, 0),
            Evaluate=counts.get(RadarRing.EVALUATE.value, 0),
            Watch=counts.get(RadarRing.WATCH.value, 0),
            Ignore=counts.get(RadarRing.IGNORE.value, 0),
        ),
        include_ignore=False,
    )


def _serialize_artifact_detail(artifact: Artifact, *, now: datetime) -> ArtifactDetailResponse:
    """Mirror radar/api/routes/ecosystem.py:get_ecosystem_artifact without the HTTP layer."""
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
        _event_to_item(event, artifact, refs_by_id[event.artifact_ref_id])
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


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _public_item_ids(board: BoardResponse) -> list[int]:
    ids: list[int] = []
    for ring in (board.rings.Use, board.rings.Prototype, board.rings.Evaluate, board.rings.Watch):
        ids.extend(item.item_id for item in ring)
    return ids


def build_static_bundle(
    target_dir: Path | str,
    *,
    session: Session,
    config: AppConfig,
    weeks: int = 26,
) -> dict[str, Path]:
    """Write the static bundle to ``target_dir`` and return the file paths.

    Layout::

        target_dir/
          board.json                      # BoardResponse (no Ignore)
          tracks.json                     # { tracks: [{id, name, item_ids}] }
          timeline.json                   # TimelineResponse
          meta.json                       # generated_at, counts, tracks
          items/<id>.json                 # ItemDetailOut, one per public item
          ecosystem-board.json            # EcosystemBoardResponse (no Ignore)
          ecosystem-events.json           # EcosystemEventsResponse (wide window)
          ecosystem-artifacts/<id>.json   # ArtifactDetailResponse, one per artifact
    """
    out_dir = ensure_dir(Path(target_dir))
    items_dir = ensure_dir(out_dir / "items")
    artifacts_dir = ensure_dir(out_dir / "ecosystem-artifacts")

    now = utc_now()

    rows = collect_board_rows(session, decided_since=None, include_ignore=False)
    board = _serialize_board(rows, now=now)
    tracks_payload = _serialize_tracks(board, config)
    timeline = collect_timeline(session, weeks=weeks, now=now)

    paths: dict[str, Path] = {
        "board": out_dir / "board.json",
        "tracks": out_dir / "tracks.json",
        "timeline": out_dir / "timeline.json",
        "meta": out_dir / "meta.json",
        "ecosystem-board": out_dir / "ecosystem-board.json",
        "ecosystem-events": out_dir / "ecosystem-events.json",
    }

    _write_json(paths["board"], board.model_dump(mode="json"))
    _write_json(paths["tracks"], tracks_payload)
    _write_json(paths["timeline"], timeline.model_dump(mode="json"))

    public_ids = _public_item_ids(board)
    items: Iterable[Item] = (
        session.scalars(select(Item).where(Item.id.in_(public_ids))).all() if public_ids else []
    )
    item_paths: list[Path] = []
    for item in items:
        detail = _serialize_item_detail(session, item, now=now)
        item_path = items_dir / f"{item.id}.json"
        _write_json(item_path, detail.model_dump(mode="json"))
        item_paths.append(item_path)

    # --- Ecosystem radar ---------------------------------------------------
    eco_rows = collect_ecosystem_board_rows(session, include_ignore=True)
    eco_board = _serialize_ecosystem_board(eco_rows, now=now)
    _write_json(paths["ecosystem-board"], eco_board.model_dump(mode="json"))

    eco_event_rows = collect_ecosystem_events(
        session,
        target_date=now.date(),
        days=ECOSYSTEM_EVENTS_WINDOW_DAYS,
        relevant_only=False,
    )
    eco_events = EcosystemEventsResponse(
        date=now.date().isoformat(),
        days=ECOSYSTEM_EVENTS_WINDOW_DAYS,
        events=[_event_to_item(event, artifact, ref) for event, artifact, ref in eco_event_rows],
    )
    _write_json(paths["ecosystem-events"], eco_events.model_dump(mode="json"))

    # One detail file per artifact — the panel reads these in static mode.
    artifacts: Iterable[Artifact] = session.scalars(
        select(Artifact).order_by(Artifact.id.asc())
    ).all()
    artifact_paths: list[Path] = []
    for artifact in artifacts:
        detail = _serialize_artifact_detail(artifact, now=now)
        artifact_path = artifacts_dir / f"{artifact.id}.json"
        _write_json(artifact_path, detail.model_dump(mode="json"))
        artifact_paths.append(artifact_path)

    meta = {
        "generated_at": now.isoformat(),
        "weeks": weeks,
        "ring_counts": board.counts.model_dump(mode="json"),
        "tracks": [
            {"id": t.id, "name": t.name, "quadrant": t.quadrant} for t in config.topics.tracks
        ],
        "items_dir": "items",
        "item_count": len(item_paths),
        "ecosystem_ring_counts": eco_board.counts.model_dump(mode="json"),
        "ecosystem_artifacts_dir": "ecosystem-artifacts",
        "ecosystem_artifact_count": len(artifact_paths),
        "ecosystem_event_count": len(eco_events.events),
    }
    _write_json(paths["meta"], meta)

    return paths
