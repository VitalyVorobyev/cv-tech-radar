"""Ecosystem fetch orchestration.

:func:`run_ecosystem_fetch` syncs the configured artifacts into the database,
polls every enabled ref, and diffs each ref's current state against the stored
:class:`ArtifactState` to emit new :class:`ArtifactEvent` rows. The whole run is
designed to be idempotent (re-polling an unchanged ref emits nothing) and
first-seen-safe (a freshly added artifact never dumps its back-catalogue).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.collectors.ecosystem import crates, github, npm, pypi
from radar.collectors.ecosystem.auth import resolve_github_token
from radar.collectors.ecosystem.base import (
    EcosystemRefResult,
    NormalizedEvent,
    build_ecosystem_client,
)
from radar.collectors.ecosystem.event_filter import classify_event
from radar.models import Artifact, ArtifactEvent, ArtifactRef, ArtifactState
from radar.schemas import AppConfig, ArtifactConfig, ArtifactsConfig
from radar.utils import utc_now

logger = logging.getLogger(__name__)

# Uniform ``fetch_ref(client, ref, *, token=None) -> EcosystemRefResult`` dispatch.
FetchRefFn = Callable[..., EcosystemRefResult]
_FETCHERS: dict[str, FetchRefFn] = {
    "github": github.fetch_ref,
    "pypi": pypi.fetch_ref,
    "crates": crates.fetch_ref,
    "npm": npm.fetch_ref,
}


@dataclass
class EcosystemFetchStats:
    """Aggregate outcome of one ``run_ecosystem_fetch`` call."""

    artifacts_synced: int = 0
    refs_polled: int = 0
    refs_ok: int = 0
    refs_not_found: int = 0
    refs_errored: int = 0
    events_created: int = 0
    # (artifact key, ecosystem, error message)
    per_ref_errors: list[tuple[str, str, str]] = field(default_factory=list)


def sync_artifacts(session: Session, artifacts_config: ArtifactsConfig) -> int:
    """Upsert ``Artifact`` and ``ArtifactRef`` rows from config.

    Mirrors ``radar.db.upsert_source``: an artifact is found-or-created by
    ``key``, its scalar fields refreshed, and ``updated_at`` bumped. Each
    artifact's refs are upserted by ``(ecosystem, ref)``; refs that no longer
    appear in config are deleted (their ``ArtifactState`` cascades away).
    Returns the number of artifacts synced.
    """
    count = 0
    for artifact_config in artifacts_config.artifacts:
        artifact = session.scalar(select(Artifact).where(Artifact.key == artifact_config.key))
        if artifact is None:
            artifact = Artifact(key=artifact_config.key)
            session.add(artifact)
        artifact.name = artifact_config.name
        artifact.description = artifact_config.description
        artifact.status = artifact_config.status
        artifact.capability = artifact_config.capability
        artifact.tracks_json = list(artifact_config.tracks)
        artifact.homepage_url = artifact_config.homepage_url
        artifact.enabled = artifact_config.enabled
        artifact.updated_at = utc_now()
        session.flush()
        _sync_artifact_refs(session, artifact, artifact_config)
        count += 1
    return count


def _sync_artifact_refs(
    session: Session, artifact: Artifact, artifact_config: ArtifactConfig
) -> None:
    """Upsert one artifact's refs and drop refs no longer in config."""
    existing = {
        (ref.ecosystem, ref.ref): ref
        for ref in session.scalars(
            select(ArtifactRef).where(ArtifactRef.artifact_id == artifact.id)
        ).all()
    }
    wanted: set[tuple[str, str]] = set()
    for ref_config in artifact_config.refs:
        pair = (ref_config.ecosystem, ref_config.ref)
        wanted.add(pair)
        ref = existing.get(pair)
        if ref is None:
            ref = ArtifactRef(
                artifact_id=artifact.id,
                ecosystem=ref_config.ecosystem,
                ref=ref_config.ref,
            )
            session.add(ref)
    for pair, ref in existing.items():
        if pair not in wanted:
            session.delete(ref)
    session.flush()


def major_version(version: str | None) -> int | None:
    """Extract the leading integer of a version, tolerating a leading ``v``.

    Returns ``None`` when no leading integer can be parsed.
    """
    if not version:
        return None
    match = re.match(r"\s*v?(\d+)", version)
    if match is None:
        return None
    return int(match.group(1))


def run_ecosystem_fetch(
    session: Session,
    config: AppConfig,
    *,
    client: httpx.Client | None = None,
    github_token: str | None = None,
) -> EcosystemFetchStats:
    """Sync artifacts, poll every enabled ref, and emit new release events.

    The poll of each ref is wrapped in try/except so a renamed, archived, or
    deleted repo records a failure and the run continues. Mirrors the structure
    of ``radar.pipeline.run_fetch_arxiv``.
    """
    stats = EcosystemFetchStats()
    stats.artifacts_synced = sync_artifacts(session, config.artifacts)

    token = github_token if github_token is not None else resolve_github_token()
    if token is None:
        logger.info("No GitHub token (CV_RADAR_GITHUB_TOKEN); GitHub runs unauthenticated.")

    owns_client = client is None
    if client is None:
        client = build_ecosystem_client()

    config_by_key = {
        artifact_config.key: artifact_config for artifact_config in config.artifacts.artifacts
    }

    try:
        for artifact_config in config.artifacts.artifacts:
            artifact = session.scalar(select(Artifact).where(Artifact.key == artifact_config.key))
            if artifact is None:
                continue
            for ref in artifact.refs:
                if not ref.enabled:
                    continue
                _poll_ref(
                    session,
                    stats,
                    artifact=artifact,
                    artifact_config=config_by_key[artifact.key],
                    ref=ref,
                    config=config,
                    client=client,
                    token=token,
                )
    finally:
        if owns_client:
            client.close()

    return stats


def _poll_ref(
    session: Session,
    stats: EcosystemFetchStats,
    *,
    artifact: Artifact,
    artifact_config: ArtifactConfig,
    ref: ArtifactRef,
    config: AppConfig,
    client: httpx.Client,
    token: str | None,
) -> None:
    """Poll one ref, update its state, and emit a new event if the version moved."""
    stats.refs_polled += 1
    fetcher = _FETCHERS.get(ref.ecosystem)
    if fetcher is None:
        stats.refs_errored += 1
        stats.per_ref_errors.append((artifact.key, ref.ecosystem, "unknown ecosystem"))
        return

    try:
        result = fetcher(client, ref.ref, token=token)
    except Exception as exc:  # noqa: BLE001 — a bad ref must not abort the run.
        result = EcosystemRefResult(status="error", error=f"unexpected: {exc}")

    state = _find_or_create_state(session, ref)
    state.last_checked_at = utc_now()

    if result.status != "ok":
        state.last_status = result.status
        state.last_error = result.error
        state.consecutive_failures += 1
        if result.status == "not_found":
            stats.refs_not_found += 1
        else:
            stats.refs_errored += 1
        stats.per_ref_errors.append((artifact.key, ref.ecosystem, result.error or result.status))
        return

    state.last_status = "ok"
    state.last_error = ""
    state.consecutive_failures = 0
    stats.refs_ok += 1

    latest = result.latest_event
    if latest is None:
        return

    if state.last_version is None:
        # First time we see this ref: record the baseline, emit nothing.
        state.last_version = latest.version
        state.last_release_at = latest.event_date
        return

    if latest.version == state.last_version:
        return

    event_type = _classify_event_type(state.last_version, latest.version)
    _emit_event(
        session,
        stats,
        artifact=artifact,
        artifact_config=artifact_config,
        ref=ref,
        config=config,
        latest=latest,
        event_type=event_type,
    )
    state.last_version = latest.version
    state.last_release_at = latest.event_date


def _classify_event_type(previous_version: str, new_version: str) -> str:
    """Return ``"major_release"`` if the major number rose, else ``"release"``."""
    prev_major = major_version(previous_version)
    new_major = major_version(new_version)
    if prev_major is not None and new_major is not None and new_major > prev_major:
        return "major_release"
    return "release"


def _emit_event(
    session: Session,
    stats: EcosystemFetchStats,
    *,
    artifact: Artifact,
    artifact_config: ArtifactConfig,
    ref: ArtifactRef,
    config: AppConfig,
    latest: NormalizedEvent,
    event_type: str,
) -> None:
    """Create one ``ArtifactEvent`` if (ref, type, version) is not already stored."""
    already = session.scalar(
        select(ArtifactEvent.id).where(
            ArtifactEvent.artifact_ref_id == ref.id,
            ArtifactEvent.event_type == event_type,
            ArtifactEvent.version == latest.version,
        )
    )
    if already is not None:
        return

    event = ArtifactEvent(
        artifact_id=artifact.id,
        artifact_ref_id=ref.id,
        event_type=event_type,
        event_date=latest.event_date,
        version=latest.version,
        summary=latest.summary,
        body=latest.body,
        url=latest.url,
        raw_payload_json=latest.raw_payload,
        created_at=utc_now(),
    )
    classify_event(
        event,
        artifact=artifact,
        artifact_config=artifact_config,
        config=config,
    )
    session.add(event)
    stats.events_created += 1


def _find_or_create_state(session: Session, ref: ArtifactRef) -> ArtifactState:
    state = session.scalar(select(ArtifactState).where(ArtifactState.artifact_ref_id == ref.id))
    if state is None:
        state = ArtifactState(artifact_ref_id=ref.id)
        session.add(state)
        session.flush()
    return state


__all__ = [
    "EcosystemFetchStats",
    "major_version",
    "run_ecosystem_fetch",
    "sync_artifacts",
]
