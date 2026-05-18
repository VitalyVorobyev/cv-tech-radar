"""PyPI release collector.

Polls ``GET https://pypi.org/pypi/{project}/json`` and reports ``info.version``
as the ref's current state. PyPI exposes no per-release changelog, so the
summary/body fall back to ``info.summary`` — a known v1 limitation.
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

ECOSYSTEM = "pypi"


def fetch_ref(client: httpx.Client, ref: str, *, token: str | None = None) -> EcosystemRefResult:
    """Fetch the latest PyPI release for project ``ref``.

    ``token`` is accepted for a uniform collector signature and ignored. Never
    raises: a 404 yields ``status="not_found"``; any other failure yields
    ``status="error"``.
    """
    url = f"https://pypi.org/pypi/{ref}/json"
    try:
        response = request_json(client, url, ecosystem=ECOSYSTEM)
    except httpx.HTTPError as exc:
        return EcosystemRefResult(status="error", error=f"request failed: {exc}")

    if response.status_code == 404:
        return EcosystemRefResult(status="not_found")
    if response.status_code != 200:
        return EcosystemRefResult(status="error", error=f"HTTP {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        return EcosystemRefResult(status="error", error=f"invalid JSON: {exc}")
    if not isinstance(payload, dict):
        return EcosystemRefResult(status="error", error="unexpected response shape")

    info = payload.get("info") or {}
    version = info.get("version") or ""
    if not version:
        return EcosystemRefResult(status="ok", latest_event=None)

    releases = payload.get("releases") or {}
    files = releases.get(version) or []
    event_date = _first_upload_time(files)
    if event_date is None:
        # A version with no published files (e.g. fully yanked) has no date.
        return EcosystemRefResult(status="ok", latest_event=None)

    summary = info.get("summary") or ""
    return EcosystemRefResult(
        status="ok",
        latest_event=NormalizedEvent(
            version=version,
            event_date=event_date,
            summary=summary,
            body=cap_body(summary),
            url=f"https://pypi.org/project/{ref}/{version}/",
            raw_payload=info,
        ),
    )


def _first_upload_time(files: list[dict[str, Any]]):
    """Return the upload time of the first file in a release, or ``None``."""
    for file_entry in files:
        if not isinstance(file_entry, dict):
            continue
        raw = file_entry.get("upload_time_iso_8601") or file_entry.get("upload_time")
        if raw:
            try:
                return parse_timestamp(raw)
            except ValueError:
                return None
    return None


__all__ = ["ECOSYSTEM", "fetch_ref"]
