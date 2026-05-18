"""Offline tests for the ecosystem fetch runner — diffing and idempotency.

These exercise ``run_ecosystem_fetch`` against the ``db_engine`` fixture with a
fake fetcher injected into ``runner._FETCHERS`` so no network is touched. The
fake returns canned ``EcosystemRefResult`` objects keyed by ecosystem.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from radar.collectors.ecosystem import runner as runner_module
from radar.collectors.ecosystem.base import EcosystemRefResult, NormalizedEvent
from radar.collectors.ecosystem.runner import EcosystemFetchStats, run_ecosystem_fetch
from radar.db import session_scope
from radar.models import Artifact, ArtifactEvent, ArtifactState


def _event(version: str, *, date: datetime | None = None, body: str = "") -> NormalizedEvent:
    return NormalizedEvent(
        version=version,
        event_date=date or datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        summary=f"release {version}",
        body=body,
        url=f"https://example.test/{version}",
        raw_payload={"version": version},
    )


@pytest.fixture
def single_artifact_config(app_config):
    """An app config whose ``artifacts`` list is reduced to a single artifact.

    AppConfig is immutable, so we copy it and swap one validated artifact in.
    """
    artifact = next(a for a in app_config.artifacts.artifacts if a.key == "opencv")
    new_artifacts = app_config.artifacts.model_copy(update={"artifacts": [artifact]})
    return app_config.model_copy(update={"artifacts": new_artifacts})


def _install_fake_fetchers(monkeypatch, results_by_ecosystem: dict[str, EcosystemRefResult]):
    """Replace runner._FETCHERS with fakes returning the supplied results."""

    def make(ecosystem: str):
        def fake_fetch(_client, _ref, *, token=None):  # noqa: ARG001
            return results_by_ecosystem[ecosystem]

        return fake_fetch

    fakes = {ecosystem: make(ecosystem) for ecosystem in results_by_ecosystem}
    monkeypatch.setattr(runner_module, "_FETCHERS", fakes)


def _run(db_engine, config) -> EcosystemFetchStats:
    with session_scope(db_engine) as session:
        return run_ecosystem_fetch(session, config, client=object(), github_token=None)


def test_first_poll_records_state_and_creates_no_events(
    db_engine, single_artifact_config, monkeypatch
):
    _install_fake_fetchers(
        monkeypatch,
        {
            "github": EcosystemRefResult(status="ok", latest_event=_event("4.11.0")),
            "pypi": EcosystemRefResult(status="ok", latest_event=_event("4.11.0.84")),
        },
    )
    stats = _run(db_engine, single_artifact_config)

    assert stats.artifacts_synced == 1
    assert stats.refs_polled == 2
    assert stats.refs_ok == 2
    # First-seen suppression: the baseline is recorded, no backlog is emitted.
    assert stats.events_created == 0

    with session_scope(db_engine) as session:
        states = session.scalars(select(ArtifactState)).all()
        assert {s.last_version for s in states} == {"4.11.0", "4.11.0.84"}
        assert session.scalars(select(ArtifactEvent)).all() == []


def test_second_poll_same_version_is_idempotent(db_engine, single_artifact_config, monkeypatch):
    results = {
        "github": EcosystemRefResult(status="ok", latest_event=_event("4.11.0")),
        "pypi": EcosystemRefResult(status="ok", latest_event=_event("4.11.0.84")),
    }
    _install_fake_fetchers(monkeypatch, results)
    _run(db_engine, single_artifact_config)
    # A second identical poll must not emit any new events.
    stats = _run(db_engine, single_artifact_config)
    assert stats.events_created == 0

    with session_scope(db_engine) as session:
        assert session.scalars(select(ArtifactEvent)).all() == []


def test_higher_version_creates_exactly_one_event(db_engine, single_artifact_config, monkeypatch):
    _install_fake_fetchers(
        monkeypatch,
        {
            "github": EcosystemRefResult(status="ok", latest_event=_event("4.11.0")),
            "pypi": EcosystemRefResult(status="ok", latest_event=_event("4.11.0.84")),
        },
    )
    _run(db_engine, single_artifact_config)

    # Only the GitHub ref moves to a new minor version.
    _install_fake_fetchers(
        monkeypatch,
        {
            "github": EcosystemRefResult(status="ok", latest_event=_event("4.11.1")),
            "pypi": EcosystemRefResult(status="ok", latest_event=_event("4.11.0.84")),
        },
    )
    stats = _run(db_engine, single_artifact_config)
    assert stats.events_created == 1

    with session_scope(db_engine) as session:
        events = session.scalars(select(ArtifactEvent)).all()
        assert len(events) == 1
        assert events[0].version == "4.11.1"
        assert events[0].event_type == "release"


def test_major_version_bump_yields_major_release(db_engine, single_artifact_config, monkeypatch):
    _install_fake_fetchers(
        monkeypatch,
        {
            "github": EcosystemRefResult(status="ok", latest_event=_event("4.11.0")),
            "pypi": EcosystemRefResult(status="ok", latest_event=_event("4.11.0.84")),
        },
    )
    _run(db_engine, single_artifact_config)

    _install_fake_fetchers(
        monkeypatch,
        {
            "github": EcosystemRefResult(status="ok", latest_event=_event("5.0.0")),
            "pypi": EcosystemRefResult(status="ok", latest_event=_event("4.11.0.84")),
        },
    )
    stats = _run(db_engine, single_artifact_config)
    assert stats.events_created == 1

    with session_scope(db_engine) as session:
        event = session.scalar(select(ArtifactEvent))
        assert event is not None
        assert event.event_type == "major_release"
        # opencv is an adopted artifact, so a major release is relevant + high severity.
        assert event.relevant is True
        assert event.severity == "high"


def test_not_found_ref_does_not_abort_run_and_is_counted(
    db_engine, single_artifact_config, monkeypatch
):
    _install_fake_fetchers(
        monkeypatch,
        {
            "github": EcosystemRefResult(status="not_found", error="HTTP 404"),
            "pypi": EcosystemRefResult(status="ok", latest_event=_event("4.11.0.84")),
        },
    )
    stats = _run(db_engine, single_artifact_config)

    # The not_found ref is counted; the other ref is still polled successfully.
    assert stats.refs_polled == 2
    assert stats.refs_not_found == 1
    assert stats.refs_ok == 1
    assert len(stats.per_ref_errors) == 1
    assert stats.per_ref_errors[0][0] == "opencv"
    assert stats.per_ref_errors[0][1] == "github"

    with session_scope(db_engine) as session:
        github_ref_state = session.scalar(
            select(ArtifactState)
            .join(ArtifactState.artifact_ref)
            .where(ArtifactState.artifact_ref.has(ecosystem="github"))
        )
        assert github_ref_state is not None
        assert github_ref_state.last_status == "not_found"
        assert github_ref_state.consecutive_failures == 1


def test_fetcher_exception_is_caught_and_recorded(db_engine, single_artifact_config, monkeypatch):
    def boom(_client, _ref, *, token=None):  # noqa: ARG001
        raise RuntimeError("simulated collector crash")

    monkeypatch.setattr(
        runner_module,
        "_FETCHERS",
        {
            "github": boom,
            "pypi": lambda *_a, **_k: EcosystemRefResult(
                status="ok", latest_event=_event("4.11.0.84")
            ),
        },
    )
    stats = _run(db_engine, single_artifact_config)
    # The crash is caught, recorded as an error, and the run continues.
    assert stats.refs_errored == 1
    assert stats.refs_ok == 1
    assert stats.per_ref_errors[0][1] == "github"


def test_sync_artifacts_prunes_removed_refs(db_engine, single_artifact_config, monkeypatch):
    _install_fake_fetchers(
        monkeypatch,
        {
            "github": EcosystemRefResult(status="ok", latest_event=_event("4.11.0")),
            "pypi": EcosystemRefResult(status="ok", latest_event=_event("4.11.0.84")),
        },
    )
    _run(db_engine, single_artifact_config)

    # Drop the pypi ref from the artifact's config and re-sync.
    artifact_cfg = single_artifact_config.artifacts.artifacts[0]
    trimmed_cfg = artifact_cfg.model_copy(
        update={"refs": [r for r in artifact_cfg.refs if r.ecosystem == "github"]}
    )
    trimmed_artifacts = single_artifact_config.artifacts.model_copy(
        update={"artifacts": [trimmed_cfg]}
    )
    trimmed_config = single_artifact_config.model_copy(update={"artifacts": trimmed_artifacts})

    _install_fake_fetchers(
        monkeypatch,
        {"github": EcosystemRefResult(status="ok", latest_event=_event("4.11.0"))},
    )
    _run(db_engine, trimmed_config)

    with session_scope(db_engine) as session:
        artifact = session.scalar(select(Artifact).where(Artifact.key == "opencv"))
        assert artifact is not None
        assert {ref.ecosystem for ref in artifact.refs} == {"github"}
