"""Regression-pin the artifact event relevance rule.

These lock the behavior of ``classify_event``: a keyword hit, an adopted
artifact, a major release, and the ``track_major_only`` override each map to a
specific ``relevant`` / ``severity`` outcome.
"""

from __future__ import annotations

from datetime import UTC, datetime

from radar.collectors.ecosystem.event_filter import classify_event
from radar.models import Artifact, ArtifactEvent
from radar.schemas import ArtifactConfig, ArtifactRefConfig


def _event(*, event_type: str, summary: str = "", body: str = "") -> ArtifactEvent:
    return ArtifactEvent(
        artifact_id=1,
        artifact_ref_id=1,
        event_type=event_type,
        event_date=datetime(2026, 5, 1, tzinfo=UTC),
        version="1.2.3",
        summary=summary,
        body=body,
        url="https://example.test/release",
    )


def _artifact(*, status: str, tracks: list[str]) -> Artifact:
    return Artifact(
        key="x",
        name="X",
        status=status,
        capability="cv-imaging",
        tracks_json=tracks,
    )


def _artifact_config(
    *,
    status: str,
    tracks: list[str],
    extra_keywords: list[str] | None = None,
    track_major_only: bool = False,
) -> ArtifactConfig:
    return ArtifactConfig(
        key="x",
        name="X",
        status=status,
        capability="cv-imaging",
        tracks=tracks,
        refs=[ArtifactRefConfig(ecosystem="github", ref="owner/x")],
        extra_keywords=extra_keywords or [],
        track_major_only=track_major_only,
    )


def test_track_keyword_in_body_marks_event_relevant(app_config):
    # "fiducial" is a positive keyword of the "Target Detection & Fiducials" track.
    tracks = ["Target Detection & Fiducials"]
    event = _event(
        event_type="release",
        summary="Minor release",
        body="Improved fiducial marker detection accuracy.",
    )
    classify_event(
        event,
        artifact=_artifact(status="watchlist", tracks=tracks),
        artifact_config=_artifact_config(status="watchlist", tracks=tracks),
        config=app_config,
    )
    assert event.relevant is True
    assert event.severity == "medium"
    assert "fiducial" in event.matched_keywords_json


def test_extra_keyword_match_marks_event_relevant(app_config):
    event = _event(
        event_type="release",
        summary="Patch release",
        body="Fixes a regression in charuco board pose recovery.",
    )
    classify_event(
        event,
        artifact=_artifact(status="watchlist", tracks=[]),
        artifact_config=_artifact_config(status="watchlist", tracks=[], extra_keywords=["charuco"]),
        config=app_config,
    )
    assert event.relevant is True
    assert "charuco" in event.matched_keywords_json


def test_watchlist_release_with_no_keyword_hit_is_not_relevant(app_config):
    event = _event(
        event_type="release",
        summary="Routine maintenance release",
        body="Dependency bumps and CI cleanup.",
    )
    classify_event(
        event,
        artifact=_artifact(status="watchlist", tracks=["Target Detection & Fiducials"]),
        artifact_config=_artifact_config(
            status="watchlist", tracks=["Target Detection & Fiducials"]
        ),
        config=app_config,
    )
    assert event.relevant is False
    assert event.severity == "low"
    assert event.matched_keywords_json == []


def test_adopted_artifact_plain_release_is_relevant(app_config):
    event = _event(
        event_type="release",
        summary="Routine maintenance release",
        body="Dependency bumps and CI cleanup.",
    )
    classify_event(
        event,
        artifact=_artifact(status="adopted", tracks=[]),
        artifact_config=_artifact_config(status="adopted", tracks=[]),
        config=app_config,
    )
    # An adopted dependency moving at all is worth surfacing.
    assert event.relevant is True
    assert event.severity == "medium"


def test_major_release_is_relevant_and_high_severity(app_config):
    event = _event(
        event_type="major_release",
        summary="Major version bump",
        body="Breaking API changes.",
    )
    classify_event(
        event,
        artifact=_artifact(status="watchlist", tracks=[]),
        artifact_config=_artifact_config(status="watchlist", tracks=[]),
        config=app_config,
    )
    assert event.relevant is True
    assert event.severity == "high"


def test_track_major_only_suppresses_non_major_release(app_config):
    # The body contains a track keyword that would otherwise mark it relevant.
    tracks = ["Target Detection & Fiducials"]
    event = _event(
        event_type="release",
        summary="Minor release",
        body="Improved fiducial marker detection.",
    )
    classify_event(
        event,
        artifact=_artifact(status="adopted", tracks=tracks),
        artifact_config=_artifact_config(status="adopted", tracks=tracks, track_major_only=True),
        config=app_config,
    )
    # track_major_only forces a non-major release to irrelevant / low...
    assert event.relevant is False
    assert event.severity == "low"
    # ...but the matched keywords are still preserved for transparency.
    assert "fiducial" in event.matched_keywords_json


def test_track_major_only_still_allows_major_release(app_config):
    event = _event(event_type="major_release", summary="v2", body="Breaking changes.")
    classify_event(
        event,
        artifact=_artifact(status="adopted", tracks=[]),
        artifact_config=_artifact_config(status="adopted", tracks=[], track_major_only=True),
        config=app_config,
    )
    assert event.relevant is True
    assert event.severity == "high"
