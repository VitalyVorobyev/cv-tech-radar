from __future__ import annotations

import json
from datetime import UTC, date, datetime

from sqlalchemy import select

from radar.db import session_scope
from radar.models import Artifact, ArtifactEvent, ArtifactRef, Digest, Item, RadarDecision
from radar.reports.digest import (
    collect_digest_rows,
    render_digest_markdown,
    write_digest_outputs,
)
from radar.schemas import RadarRing


def _ecosystem_row(
    *,
    event_id: int = 1,
    name: str = "OpenCV",
    ecosystem: str = "github",
    version: str = "5.0.0",
    event_type: str = "major_release",
    summary: str = "OpenCV 5 released.",
) -> tuple[ArtifactEvent, Artifact, ArtifactRef]:
    artifact = Artifact(key=name.lower(), name=name, status="adopted", capability="cv-imaging")
    ref = ArtifactRef(ecosystem=ecosystem, ref=f"{name.lower()}/{name.lower()}")
    event = ArtifactEvent(
        id=event_id,
        event_type=event_type,
        event_date=datetime(2026, 5, 16, tzinfo=UTC),
        version=version,
        summary=summary,
        url=f"https://example.test/{name.lower()}-{version}",
        severity="high",
    )
    return event, artifact, ref


def test_digest_renders_ecosystem_section_with_no_paper_decisions():
    markdown = render_digest_markdown(
        [], date(2026, 5, 17), days=1, ecosystem_events=[_ecosystem_row()]
    )
    assert "## Ecosystem" in markdown
    assert "**OpenCV** 5.0.0 — major release (github)" in markdown
    assert "OpenCV 5 released." in markdown


def test_digest_ecosystem_section_empty_when_no_events():
    markdown = render_digest_markdown([], date(2026, 5, 17), days=1)
    assert "## Ecosystem" in markdown
    assert "_No release events for window._" in markdown


def test_write_digest_outputs_includes_ecosystem_events_in_json(db_engine, tmp_path):
    target = date(2026, 5, 17)
    with session_scope(db_engine) as session:
        report_path, export_path = write_digest_outputs(
            session,
            [],
            target,
            days=1,
            reports_dir=tmp_path / "d",
            exports_dir=tmp_path / "e",
            ecosystem_events=[_ecosystem_row()],
        )
    payload = json.loads(export_path.read_text())
    assert len(payload["ecosystem_events"]) == 1
    entry = payload["ecosystem_events"][0]
    assert entry["artifact_key"] == "opencv"
    assert entry["version"] == "5.0.0"
    assert entry["ecosystem"] == "github"
    assert "## Ecosystem" in report_path.read_text()


def _add_item(session, *, item_id: int, title: str, published: datetime) -> None:
    session.add(
        Item(
            id=item_id,
            type="paper",
            title=title,
            normalized_title=title.casefold(),
            abstract_or_summary="",
            url=f"https://example.test/{item_id}",
            pdf_url=None,
            published_at=published,
            updated_at=None,
            source_name="arXiv cs.CV",
            external_id=f"ext-{item_id}",
            arxiv_id=f"ext-{item_id}",
            authors_json=[],
            organizations_json=[],
            metadata_json={},
        )
    )


def _add_decision(
    session,
    *,
    item_id: int,
    ring: RadarRing,
    tracks: list[str],
    reason: str,
    created_at: datetime,
    uncertain: bool = False,
) -> None:
    session.add(
        RadarDecision(
            item_id=item_id,
            ring=ring.value,
            tracks_json=tracks,
            decision_reason=reason,
            action="",
            decided_by="tester",
            uncertain=uncertain,
            created_at=created_at,
        )
    )


def test_digest_empty_window_writes_stub(db_engine, tmp_path):
    target = date(2026, 5, 11)
    with session_scope(db_engine) as session:
        rows = collect_digest_rows(session, target, days=1)
        report_path, export_path = write_digest_outputs(
            session,
            rows,
            target,
            days=1,
            reports_dir=tmp_path / "digests",
            exports_dir=tmp_path / "digest-exports",
        )
    markdown = report_path.read_text()
    assert "No decisions for window" in markdown
    payload = json.loads(export_path.read_text())
    assert payload["rows"] == []
    with session_scope(db_engine) as session:
        digest_dates = [d.date for d in session.scalars(select(Digest)).all()]
    assert digest_dates == ["2026-05-11"]


def test_digest_mixed_rings_section_order(db_engine, tmp_path):
    target = date(2026, 5, 11)
    published = datetime(2026, 5, 11, 10, tzinfo=UTC)
    decided = datetime(2026, 5, 11, 12, tzinfo=UTC)
    with session_scope(db_engine) as session:
        _add_item(session, item_id=1, title="Use Item", published=published)
        _add_item(session, item_id=2, title="Proto Item", published=published)
        _add_item(session, item_id=3, title="Watch Item", published=published)
        for ignore_id in (10, 11, 12, 13):
            _add_item(session, item_id=ignore_id, title=f"Ignore {ignore_id}", published=published)
        session.flush()
        _add_decision(
            session,
            item_id=1,
            ring=RadarRing.USE,
            tracks=["Calibration"],
            reason="ship",
            created_at=decided,
        )
        _add_decision(
            session,
            item_id=2,
            ring=RadarRing.PROTOTYPE,
            tracks=["3D Geometry"],
            reason="try",
            created_at=decided,
        )
        _add_decision(
            session,
            item_id=3,
            ring=RadarRing.WATCH,
            tracks=["Object Tracking"],
            reason="watch",
            created_at=decided,
        )
        for ignore_id in (10, 11, 12, 13):
            _add_decision(
                session,
                item_id=ignore_id,
                ring=RadarRing.IGNORE,
                tracks=[],
                reason="noise",
                created_at=decided,
            )

    with session_scope(db_engine) as session:
        rows = collect_digest_rows(session, target, days=1)
        markdown = render_digest_markdown(rows, target, days=1)

    assert markdown.index("## Use") < markdown.index("## Prototype")
    assert markdown.index("## Prototype") < markdown.index("## Evaluate")
    assert markdown.index("## Evaluate") < markdown.index("## Watch")
    assert markdown.index("## Watch") < markdown.index("## Ignore (4)")
    assert markdown.index("## Ignore (4)") < markdown.index("## Uncertainty")
    # Ignore section should only preview 3 titles
    ignore_section = markdown.split("## Ignore (4)", 1)[1].split("##", 1)[0]
    preview_lines = [ln for ln in ignore_section.splitlines() if ln.startswith("- ")]
    assert len(preview_lines) == 3


def test_digest_days_window(db_engine, tmp_path):
    target = date(2026, 5, 11)
    with session_scope(db_engine) as session:
        _add_item(
            session,
            item_id=1,
            title="Today",
            published=datetime(2026, 5, 11, 10, tzinfo=UTC),
        )
        _add_item(
            session,
            item_id=2,
            title="Two Days Ago",
            published=datetime(2026, 5, 9, 10, tzinfo=UTC),
        )
        session.flush()
        decided = datetime(2026, 5, 11, 12, tzinfo=UTC)
        _add_decision(
            session,
            item_id=1,
            ring=RadarRing.WATCH,
            tracks=[],
            reason="r1",
            created_at=decided,
        )
        _add_decision(
            session,
            item_id=2,
            ring=RadarRing.WATCH,
            tracks=[],
            reason="r2",
            created_at=decided,
        )

    with session_scope(db_engine) as session:
        ids_one = {item.id for item, _ in collect_digest_rows(session, target, days=1)}
        ids_three = {item.id for item, _ in collect_digest_rows(session, target, days=3)}
    assert ids_one == {1}
    assert ids_three == {1, 2}


def test_digest_latest_decision_wins(db_engine):
    target = date(2026, 5, 11)
    with session_scope(db_engine) as session:
        _add_item(
            session,
            item_id=1,
            title="Item",
            published=datetime(2026, 5, 11, 10, tzinfo=UTC),
        )
        session.flush()
        _add_decision(
            session,
            item_id=1,
            ring=RadarRing.WATCH,
            tracks=[],
            reason="first",
            created_at=datetime(2026, 5, 11, 11, tzinfo=UTC),
        )
        _add_decision(
            session,
            item_id=1,
            ring=RadarRing.PROTOTYPE,
            tracks=[],
            reason="second",
            created_at=datetime(2026, 5, 11, 13, tzinfo=UTC),
        )
    with session_scope(db_engine) as session:
        rows = collect_digest_rows(session, target, days=1)
        latest_rings = [decision.ring for _, decision in rows]
    assert latest_rings == ["Prototype"]


def test_digest_uncertain_surfaces(db_engine):
    target = date(2026, 5, 11)
    with session_scope(db_engine) as session:
        _add_item(
            session,
            item_id=1,
            title="Uncertain Item",
            published=datetime(2026, 5, 11, 10, tzinfo=UTC),
        )
        session.flush()
        _add_decision(
            session,
            item_id=1,
            ring=RadarRing.WATCH,
            tracks=[],
            reason="hmm",
            created_at=datetime(2026, 5, 11, 12, tzinfo=UTC),
            uncertain=True,
        )
    with session_scope(db_engine) as session:
        rows = collect_digest_rows(session, target, days=1)
        markdown = render_digest_markdown(rows, target, days=1)
    uncertainty_block = markdown.split("## Uncertainty / Open Questions", 1)[1]
    assert "Uncertain Item" in uncertainty_block


def test_digest_rerun_upserts_single_row(db_engine, tmp_path):
    target = date(2026, 5, 11)
    with session_scope(db_engine) as session:
        rows = collect_digest_rows(session, target, days=1)
        write_digest_outputs(
            session,
            rows,
            target,
            days=1,
            reports_dir=tmp_path / "d1",
            exports_dir=tmp_path / "e1",
        )
    with session_scope(db_engine) as session:
        rows = collect_digest_rows(session, target, days=1)
        write_digest_outputs(
            session,
            rows,
            target,
            days=1,
            reports_dir=tmp_path / "d2",
            exports_dir=tmp_path / "e2",
        )
    with session_scope(db_engine) as session:
        digests = session.scalars(select(Digest)).all()
        digest_paths = [d.markdown_path for d in digests]
    assert len(digest_paths) == 1
    assert digest_paths[0].endswith("/d2/2026-05-11.md")
