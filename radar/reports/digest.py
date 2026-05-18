from __future__ import annotations

import json
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from radar.models import (
    Artifact,
    ArtifactEvent,
    ArtifactRef,
    Digest,
    Item,
    ItemClassification,
    RadarDecision,
)
from radar.schemas import RadarRing
from radar.utils import date_window_bounds, ensure_dir, utc_now

# Rows as returned by radar.reports.ecosystem.collect_ecosystem_events.
EcosystemEventRow = tuple[ArtifactEvent, Artifact, ArtifactRef]

DIGEST_RING_ORDER: tuple[RadarRing, ...] = (
    RadarRing.USE,
    RadarRing.PROTOTYPE,
    RadarRing.EVALUATE,
    RadarRing.WATCH,
)
IGNORE_PREVIEW_LIMIT = 3


def collect_digest_rows(
    session: Session,
    target_date: date,
    days: int,
) -> list[tuple[Item, RadarDecision]]:
    start, end = date_window_bounds(target_date, days)
    rows = session.execute(
        select(Item, RadarDecision)
        .join(RadarDecision, RadarDecision.item_id == Item.id)
        .where(Item.published_at >= start, Item.published_at <= end)
        .order_by(RadarDecision.created_at.desc())
    ).all()

    latest_per_item: OrderedDict[int, tuple[Item, RadarDecision]] = OrderedDict()
    for item, decision in rows:
        if item.id not in latest_per_item:
            latest_per_item[item.id] = (item, decision)
    return list(latest_per_item.values())


def collect_board_rows(
    session: Session,
    *,
    decided_since: datetime | None = None,
    include_ignore: bool = False,
) -> list[tuple[Item, RadarDecision, float | None]]:
    """Return (item, latest decision, latest final_score) for items currently on the radar.

    "Currently on the radar" means: each item is represented by its most-recent
    decision regardless of when the item was published. This is the persistent
    view — items decided weeks ago still appear here.

    - decided_since: if set, drop items whose latest decision is older than this.
    - include_ignore: defaults False — the board is about attention, not the slush pile.
    """
    latest_decision_subq = (
        select(
            RadarDecision.item_id,
            func.max(RadarDecision.created_at).label("max_created"),
        )
        .group_by(RadarDecision.item_id)
        .subquery()
    )
    decision_alias = aliased(RadarDecision)
    stmt = (
        select(Item, decision_alias, ItemClassification.final_score)
        .join(latest_decision_subq, latest_decision_subq.c.item_id == Item.id)
        .join(
            decision_alias,
            (decision_alias.item_id == latest_decision_subq.c.item_id)
            & (decision_alias.created_at == latest_decision_subq.c.max_created),
        )
        .outerjoin(ItemClassification, ItemClassification.item_id == Item.id)
        # id DESC tiebreaker keeps the winner deterministic when two decisions
        # share the same created_at (a real case on SQLite's sub-second clock).
        .order_by(decision_alias.created_at.desc(), decision_alias.id.desc())
    )
    if decided_since is not None:
        stmt = stmt.where(decision_alias.created_at >= decided_since)
    if not include_ignore:
        stmt = stmt.where(decision_alias.ring != RadarRing.IGNORE.value)

    # Multiple decisions can share the exact same created_at timestamp on test SQLite
    # (sub-second resolution issues). Dedupe by item_id with first-wins.
    seen: set[int] = set()
    out: list[tuple[Item, RadarDecision, float | None]] = []
    for item, decision, score in session.execute(stmt).all():
        if item.id in seen:
            continue
        seen.add(item.id)
        out.append((item, decision, score))
    return out


def render_digest_markdown(
    rows: list[tuple[Item, RadarDecision]],
    target_date: date,
    days: int,
    *,
    ecosystem_events: list[EcosystemEventRow] | None = None,
) -> str:
    ecosystem_events = ecosystem_events or []
    window_label = f"window: {days} day{'s' if days != 1 else ''}"
    lines: list[str] = [
        f"# Daily Digest — {target_date.isoformat()} ({window_label})",
        "",
    ]
    if not rows:
        lines.extend(["_No decisions for window._", ""])
        _append_ecosystem_section(lines, ecosystem_events)
        return "\n".join(lines)

    by_ring: dict[str, list[tuple[Item, RadarDecision]]] = {ring.value: [] for ring in RadarRing}
    for item, decision in rows:
        by_ring.setdefault(decision.ring, []).append((item, decision))

    for ring in DIGEST_RING_ORDER:
        lines.append(f"## {ring.value}")
        lines.append("")
        bucket = by_ring.get(ring.value, [])
        if not bucket:
            lines.extend(["_No items._", ""])
            continue
        for item, decision in bucket:
            lines.extend(_render_item_block(item, decision))
        lines.append("")

    ignore_bucket = by_ring.get(RadarRing.IGNORE.value, [])
    lines.append(f"## Ignore ({len(ignore_bucket)})")
    lines.append("")
    if not ignore_bucket:
        lines.extend(["_No items._", ""])
    else:
        lines.append("Representative titles:")
        for item, _ in ignore_bucket[:IGNORE_PREVIEW_LIMIT]:
            lines.append(f"- {item.title}")
        lines.append("")

    _append_ecosystem_section(lines, ecosystem_events)

    uncertain_rows = [(item, dec) for item, dec in rows if dec.uncertain]
    lines.append("## Uncertainty / Open Questions")
    lines.append("")
    if not uncertain_rows:
        lines.extend(["_None flagged._", ""])
    else:
        for item, decision in uncertain_rows:
            lines.extend(_render_item_block(item, decision, include_ring=True))
        lines.append("")

    return "\n".join(lines)


def _render_item_block(
    item: Item,
    decision: RadarDecision,
    *,
    include_ring: bool = False,
) -> list[str]:
    tracks = ", ".join(decision.tracks_json or []) or "—"
    prefix = f"[{decision.ring}] " if include_ring else ""
    block = [
        f"- **{prefix}{item.title}** ([link]({item.url}))",
        f"  Tracks: {tracks}",
    ]
    if decision.decision_reason:
        block.append(f"  Reason: {decision.decision_reason}")
    if decision.action:
        block.append(f"  Action: {decision.action}")
    return block


_EVENT_TYPE_LABELS = {"major_release": "major release", "release": "release"}


def _append_ecosystem_section(lines: list[str], events: list[EcosystemEventRow]) -> None:
    """Append the ``## Ecosystem`` section — relevant release events for the window.

    The ecosystem lane has no per-event curator decision (events are surfaced
    straight from the relevance filter), so this lists ``relevant`` events as
    collected, newest first.
    """
    lines.append("## Ecosystem")
    lines.append("")
    if not events:
        lines.extend(["_No release events for window._", ""])
        return
    for event, artifact, ref in events:
        version = event.version or "—"
        label = _EVENT_TYPE_LABELS.get(event.event_type, event.event_type.replace("_", " "))
        lines.append(
            f"- **{artifact.name}** {version} — {label} ({ref.ecosystem}) ([link]({event.url}))"
        )
        if event.summary:
            lines.append(f"  {event.summary}")
    lines.append("")


def write_digest_outputs(
    session: Session,
    rows: list[tuple[Item, RadarDecision]],
    target_date: date,
    days: int,
    *,
    reports_dir: Path | str = Path("reports/digests"),
    exports_dir: Path | str = Path("data/exports/digests"),
    ecosystem_events: list[EcosystemEventRow] | None = None,
) -> tuple[Path, Path]:
    ecosystem_events = ecosystem_events or []
    report_path = ensure_dir(Path(reports_dir)) / f"{target_date.isoformat()}.md"
    export_path = ensure_dir(Path(exports_dir)) / f"{target_date.isoformat()}.json"
    markdown = render_digest_markdown(rows, target_date, days, ecosystem_events=ecosystem_events)
    report_path.write_text(markdown, encoding="utf-8")

    export_payload = {
        "generated_at": utc_now().isoformat(),
        "date": target_date.isoformat(),
        "days": days,
        "rows": [
            {
                "item_id": item.id,
                "title": item.title,
                "url": item.url,
                "ring": decision.ring,
                "tracks": decision.tracks_json or [],
                "reason": decision.decision_reason,
                "action": decision.action,
                "uncertain": bool(decision.uncertain),
                "decided_by": decision.decided_by,
                "decision_created_at": decision.created_at.isoformat()
                if decision.created_at
                else None,
            }
            for item, decision in rows
        ],
        "ecosystem_events": [
            {
                "event_id": event.id,
                "artifact_key": artifact.key,
                "artifact_name": artifact.name,
                "ecosystem": ref.ecosystem,
                "event_type": event.event_type,
                "version": event.version,
                "severity": event.severity,
                "url": event.url,
                "summary": event.summary,
                "event_date": event.event_date.isoformat() if event.event_date else None,
            }
            for event, artifact, ref in ecosystem_events
        ],
    }
    export_path.write_text(
        json.dumps(export_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    upsert_digest_row(
        session,
        kind="daily",
        target_date=target_date,
        title=f"Daily Digest {target_date.isoformat()}",
        markdown_path=str(report_path),
        json_path=str(export_path),
    )
    return report_path, export_path


def upsert_digest_row(
    session: Session,
    *,
    kind: str,
    target_date: date,
    title: str,
    markdown_path: str,
    json_path: str | None,
) -> Digest:
    date_key = target_date.isoformat()
    existing = session.scalar(select(Digest).where(Digest.kind == kind, Digest.date == date_key))
    now = utc_now()
    if existing is None:
        digest = Digest(
            kind=kind,
            date=date_key,
            title=title,
            markdown_path=markdown_path,
            json_path=json_path,
            created_at=now,
            updated_at=now,
        )
        session.add(digest)
        session.flush()
        return digest
    existing.title = title
    existing.markdown_path = markdown_path
    existing.json_path = json_path
    existing.updated_at = now
    session.flush()
    return existing
