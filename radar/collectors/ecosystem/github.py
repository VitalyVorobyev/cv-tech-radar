"""GitHub releases collector.

Polls ``GET /repos/{owner}/{repo}/releases`` and reports the newest published,
non-draft, non-prerelease release as the ref's current state.
"""

from __future__ import annotations

from typing import Any

import httpx

from radar.collectors.ecosystem.base import (
    EcosystemRefResult,
    NormalizedEvent,
    cap_body,
    parse_timestamp,
    request_json,
)

ECOSYSTEM = "github"
_API_ROOT = "https://api.github.com"


def fetch_ref(client: httpx.Client, ref: str, *, token: str | None = None) -> EcosystemRefResult:
    """Fetch the latest GitHub release for ``ref`` (``owner/repo``).

    Never raises: a 404 yields ``status="not_found"``; any other failure yields
    ``status="error"`` with a short message. A repo with no releases yields
    ``status="ok", latest_event=None``.
    """
    url = f"{_API_ROOT}/repos/{ref}/releases"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = request_json(
            client,
            url + "?per_page=10",
            ecosystem=ECOSYSTEM,
            headers=headers,
        )
    except httpx.HTTPError as exc:
        return EcosystemRefResult(status="error", error=f"request failed: {exc}")

    if response.status_code == 404:
        return EcosystemRefResult(status="not_found")
    if response.status_code != 200:
        return EcosystemRefResult(
            status="error",
            error=f"HTTP {response.status_code}",
        )

    try:
        releases = response.json()
    except ValueError as exc:
        return EcosystemRefResult(status="error", error=f"invalid JSON: {exc}")
    if not isinstance(releases, list):
        return EcosystemRefResult(status="error", error="unexpected response shape")

    release = _pick_latest_release(releases)
    if release is None:
        return EcosystemRefResult(status="ok", latest_event=None)

    try:
        event = _normalize_release(release)
    except (KeyError, ValueError) as exc:
        return EcosystemRefResult(status="error", error=f"malformed release: {exc}")
    return EcosystemRefResult(status="ok", latest_event=event)


def _pick_latest_release(releases: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the newest published, non-draft, non-prerelease release."""
    candidates = [
        release
        for release in releases
        if isinstance(release, dict)
        and not release.get("draft", False)
        and not release.get("prerelease", False)
        and release.get("published_at")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda release: parse_timestamp(release["published_at"]))


def _normalize_release(release: dict[str, Any]) -> NormalizedEvent:
    version = release.get("tag_name") or ""
    if not version:
        msg = "release has no tag_name"
        raise ValueError(msg)
    body = cap_body(release.get("body") or "")
    return NormalizedEvent(
        version=version,
        event_date=parse_timestamp(release["published_at"]),
        summary=release.get("name") or version,
        body=body,
        url=release.get("html_url") or "",
        raw_payload=release,
    )


__all__ = ["ECOSYSTEM", "fetch_ref"]
