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
    BoardCountsOut,
    BoardItemOut,
    BoardResponse,
    BoardRingsOut,
    HistoryEntryOut,
    ItemDetailOut,
)
from radar.models import Item, RadarDecision
from radar.reports.digest import collect_board_rows
from radar.reports.timeline import collect_timeline
from radar.schemas import AppConfig, RadarRing
from radar.utils import ensure_dir, utc_now

BUNDLE_FILES = ("board.json", "tracks.json", "timeline.json", "meta.json")


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
          board.json       # BoardResponse (no Ignore)
          tracks.json      # { tracks: [{id, name, item_ids: [...]}] }
          timeline.json    # TimelineResponse
          meta.json        # generated_at, weeks, ring counts, tracks
          items/<id>.json  # ItemDetailOut, one per public item
    """
    out_dir = ensure_dir(Path(target_dir))
    items_dir = ensure_dir(out_dir / "items")

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

    meta = {
        "generated_at": now.isoformat(),
        "weeks": weeks,
        "ring_counts": board.counts.model_dump(mode="json"),
        "tracks": [
            {"id": t.id, "name": t.name, "quadrant": t.quadrant} for t in config.topics.tracks
        ],
        "items_dir": "items",
        "item_count": len(item_paths),
    }
    _write_json(paths["meta"], meta)

    return paths
