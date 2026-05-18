from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from radar.db import session_scope
from radar.models import (
    Artifact,
    ArtifactDecision,
    ArtifactEvent,
    ArtifactRef,
    ArtifactState,
    Item,
    RadarDecision,
)
from radar.reports.static_bundle import BUNDLE_FILES, build_static_bundle
from radar.schemas import RadarRing


def _add_item(
    session, *, item_id: int, title: str, published: datetime, first_decided: datetime
) -> None:
    session.add(
        Item(
            id=item_id,
            type="paper",
            title=title,
            normalized_title=title.casefold(),
            abstract_or_summary=f"abstract for {title}",
            url=f"https://example.test/{item_id}",
            pdf_url=None,
            published_at=published,
            updated_at=None,
            source_name="arXiv cs.CV",
            external_id=f"ext-{item_id}",
            arxiv_id=f"ext-{item_id}",
            authors_json=["A. Author"],
            organizations_json=[],
            metadata_json={},
            first_decided_at=first_decided,
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
    previous_ring: str | None = None,
) -> None:
    session.add(
        RadarDecision(
            item_id=item_id,
            ring=ring.value,
            tracks_json=tracks,
            decision_reason=reason,
            action="",
            decided_by="tester",
            uncertain=False,
            previous_ring=previous_ring,
            created_at=created_at,
        )
    )


def test_build_static_bundle_writes_all_files(db_engine, app_config, tmp_path):
    now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=UTC)
    decided = now - timedelta(days=1)
    published = decided - timedelta(days=2)

    with session_scope(db_engine) as session:
        _add_item(session, item_id=1, title="Use thing", published=published, first_decided=decided)
        _add_item(
            session, item_id=2, title="Proto thing", published=published, first_decided=decided
        )
        _add_item(
            session, item_id=3, title="Watch thing", published=published, first_decided=decided
        )
        _add_item(
            session, item_id=4, title="Ignored thing", published=published, first_decided=decided
        )
        session.flush()
        _add_decision(
            session,
            item_id=1,
            ring=RadarRing.USE,
            tracks=["Calibration & Camera Models", "Open-Source CV Tooling"],
            reason="ship",
            created_at=decided,
        )
        _add_decision(
            session,
            item_id=2,
            ring=RadarRing.PROTOTYPE,
            tracks=["3D Geometry & Reconstruction"],
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
        _add_decision(
            session,
            item_id=4,
            ring=RadarRing.IGNORE,
            tracks=[],
            reason="noise",
            created_at=decided,
        )

    target = tmp_path / "bundle"
    with session_scope(db_engine) as session:
        paths = build_static_bundle(target, session=session, config=app_config, weeks=4)

    for name in BUNDLE_FILES:
        assert paths[name.removesuffix(".json")].exists(), name

    board = json.loads((target / "board.json").read_text())
    assert [it["item_id"] for it in board["rings"]["Use"]] == [1]
    assert [it["item_id"] for it in board["rings"]["Prototype"]] == [2]
    assert [it["item_id"] for it in board["rings"]["Watch"]] == [3]
    assert board["rings"]["Ignore"] == []
    assert board["counts"] == {"Use": 1, "Prototype": 1, "Evaluate": 0, "Watch": 1, "Ignore": 0}

    tracks = json.loads((target / "tracks.json").read_text())
    track_index = {t["name"]: t["item_ids"] for t in tracks["tracks"]}
    assert track_index["Calibration & Camera Models"] == [1]
    assert track_index["Open-Source CV Tooling"] == [1]
    assert track_index["3D Geometry & Reconstruction"] == [2]
    assert track_index["Object Tracking"] == [3]

    timeline = json.loads((target / "timeline.json").read_text())
    assert "weeks" in timeline
    assert len(timeline["weeks"]) == 4

    meta = json.loads((target / "meta.json").read_text())
    assert meta["item_count"] == 3
    assert meta["ring_counts"]["Ignore"] == 0
    assert any(t["name"] == "Calibration & Camera Models" for t in meta["tracks"])

    items_dir = target / "items"
    item_files = sorted(p.name for p in items_dir.iterdir())
    assert item_files == ["1.json", "2.json", "3.json"]
    item1 = json.loads((items_dir / "1.json").read_text())
    assert item1["title"] == "Use thing"
    assert item1["ring"] == "Use"
    assert item1["abstract"] == "abstract for Use thing"
    assert item1["history"][-1]["ring"] == "Use"


def test_build_static_bundle_empty_db(db_engine, app_config, tmp_path):
    target = tmp_path / "empty"
    with session_scope(db_engine) as session:
        build_static_bundle(target, session=session, config=app_config, weeks=2)

    board = json.loads((target / "board.json").read_text())
    assert board["rings"]["Use"] == []
    assert board["counts"] == {"Use": 0, "Prototype": 0, "Evaluate": 0, "Watch": 0, "Ignore": 0}

    tracks = json.loads((target / "tracks.json").read_text())
    for entry in tracks["tracks"]:
        assert entry["item_ids"] == []

    timeline = json.loads((target / "timeline.json").read_text())
    assert len(timeline["weeks"]) == 2
    for week in timeline["weeks"]:
        assert week["Use"] == 0
        assert week["Watch"] == 0

    items_dir = target / "items"
    assert items_dir.exists()
    assert list(items_dir.iterdir()) == []

    meta = json.loads((target / "meta.json").read_text())
    assert meta["item_count"] == 0

    # Ecosystem files are always written, even with no artifacts.
    eco_board = json.loads((target / "ecosystem-board.json").read_text())
    assert eco_board["rings"]["Use"] == []
    assert eco_board["counts"] == {
        "Use": 0,
        "Prototype": 0,
        "Evaluate": 0,
        "Watch": 0,
        "Ignore": 0,
    }
    eco_events = json.loads((target / "ecosystem-events.json").read_text())
    assert eco_events["events"] == []
    artifacts_dir = target / "ecosystem-artifacts"
    assert artifacts_dir.exists()
    assert list(artifacts_dir.iterdir()) == []
    assert meta["ecosystem_artifact_count"] == 0
    assert meta["ecosystem_event_count"] == 0


def _add_artifact(
    session,
    *,
    artifact_id: int,
    key: str,
    name: str,
    status: str,
    capability: str,
    tracks: list[str],
) -> None:
    session.add(
        Artifact(
            id=artifact_id,
            key=key,
            name=name,
            description=f"{name} description.",
            status=status,
            capability=capability,
            tracks_json=tracks,
            homepage_url=f"https://example.test/{key}",
        )
    )


def test_build_static_bundle_writes_ecosystem_files(db_engine, app_config, tmp_path):
    now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=UTC)
    released = now - timedelta(days=3)

    with session_scope(db_engine) as session:
        # adopted -> seed ring Use; watchlist -> seed ring Watch.
        _add_artifact(
            session,
            artifact_id=1,
            key="opencv",
            name="OpenCV",
            status="adopted",
            capability="cv-imaging",
            tracks=["Open-Source CV Tooling"],
        )
        _add_artifact(
            session,
            artifact_id=2,
            key="rerun",
            name="Rerun",
            status="watchlist",
            capability="viz-3d-sensors",
            tracks=["3D Geometry & Reconstruction"],
        )
        session.flush()
        ref = ArtifactRef(id=1, artifact_id=1, ecosystem="github", ref="opencv/opencv")
        session.add(ref)
        session.flush()
        session.add(
            ArtifactState(
                artifact_ref_id=1,
                last_version="4.11.0",
                last_release_at=released,
                last_status="ok",
            )
        )
        session.add(
            ArtifactEvent(
                id=1,
                artifact_id=1,
                artifact_ref_id=1,
                event_type="release",
                event_date=released,
                version="4.11.0",
                summary="OpenCV 4.11.0",
                body="Release notes for 4.11.0.",
                url="https://example.test/opencv/4.11.0",
                severity="medium",
                relevant=True,
                matched_keywords_json=["aruco"],
            )
        )
        # A non-relevant event — the static events file ships it too so the
        # frontend's "relevant only" toggle works client-side.
        session.add(
            ArtifactEvent(
                id=2,
                artifact_id=1,
                artifact_ref_id=1,
                event_type="release",
                event_date=released - timedelta(days=1),
                version="4.10.9",
                summary="OpenCV 4.10.9",
                body="",
                url="https://example.test/opencv/4.10.9",
                severity="low",
                relevant=False,
                matched_keywords_json=[],
            )
        )
        session.flush()
        session.add(
            ArtifactDecision(
                artifact_id=1,
                ring=RadarRing.USE.value,
                tracks_json=["Open-Source CV Tooling"],
                decision_reason="Core dependency.",
                action="",
                decided_by="tester",
                uncertain=False,
                previous_ring=None,
                created_at=now - timedelta(days=1),
            )
        )

    target = tmp_path / "bundle"
    with session_scope(db_engine) as session:
        build_static_bundle(target, session=session, config=app_config, weeks=4)

    eco_board = json.loads((target / "ecosystem-board.json").read_text())
    assert [a["key"] for a in eco_board["rings"]["Use"]] == ["opencv"]
    assert [a["key"] for a in eco_board["rings"]["Watch"]] == ["rerun"]
    assert eco_board["counts"]["Use"] == 1
    assert eco_board["counts"]["Watch"] == 1
    opencv_row = eco_board["rings"]["Use"][0]
    assert opencv_row["capability"] == "cv-imaging"
    assert opencv_row["ecosystems"] == ["github"]
    assert opencv_row["latest_event"]["version"] == "4.11.0"

    eco_events = json.loads((target / "ecosystem-events.json").read_text())
    # Wide window, unfiltered — relevant + non-relevant, newest first.
    assert [e["version"] for e in eco_events["events"]] == ["4.11.0", "4.10.9"]
    assert eco_events["events"][0]["relevant"] is True
    assert eco_events["events"][1]["relevant"] is False

    artifacts_dir = target / "ecosystem-artifacts"
    artifact_files = sorted(p.name for p in artifacts_dir.iterdir())
    assert artifact_files == ["1.json", "2.json"]
    detail = json.loads((artifacts_dir / "1.json").read_text())
    assert detail["key"] == "opencv"
    assert detail["ring"] == "Use"
    assert detail["homepage_url"] == "https://example.test/opencv"
    assert [r["last_version"] for r in detail["refs"]] == ["4.11.0"]
    assert [e["version"] for e in detail["events"]] == ["4.11.0", "4.10.9"]
    assert [d["ring"] for d in detail["decisions"]] == ["Use"]
    # Uncurated artifact still gets a detail file, seeded by status.
    detail2 = json.loads((artifacts_dir / "2.json").read_text())
    assert detail2["ring"] == "Watch"
    assert detail2["decisions"] == []

    meta = json.loads((target / "meta.json").read_text())
    assert meta["ecosystem_artifact_count"] == 2
    assert meta["ecosystem_event_count"] == 2
    assert meta["ecosystem_ring_counts"]["Use"] == 1
    assert meta["ecosystem_ring_counts"]["Watch"] == 1
