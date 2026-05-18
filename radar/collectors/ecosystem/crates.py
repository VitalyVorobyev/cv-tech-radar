"""crates.io release collector.

Polls ``GET https://crates.io/api/v1/crates/{crate}`` and reports the crate's
latest stable version as the ref's current state. crates.io's crawler policy
requires a descriptive User-Agent and roughly one request per second — both
are handled by ``radar.collectors.ecosystem.base``.
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

ECOSYSTEM = "crates"


def fetch_ref(client: httpx.Client, ref: str, *, token: str | None = None) -> EcosystemRefResult:
    """Fetch the latest crates.io release for crate ``ref``.

    ``token`` is accepted for a uniform collector signature and ignored. Never
    raises: a 404 yields ``status="not_found"``; any other failure yields
    ``status="error"``.
    """
    url = f"https://crates.io/api/v1/crates/{ref}"
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

    crate = payload.get("crate") or {}
    version = (
        crate.get("max_stable_version")
        or crate.get("newest_version")
        or crate.get("max_version")
        or ""
    )
    if not version:
        return EcosystemRefResult(status="ok", latest_event=None)

    versions = payload.get("versions") or []
    version_entry = _find_version_entry(versions, version)
    event_date = _entry_created_at(version_entry)
    if event_date is None:
        return EcosystemRefResult(status="ok", latest_event=None)

    description = crate.get("description") or ""
    return EcosystemRefResult(
        status="ok",
        latest_event=NormalizedEvent(
            version=version,
            event_date=event_date,
            summary=description,
            body=cap_body(description),
            url=f"https://crates.io/crates/{ref}/{version}",
            raw_payload=version_entry or {},
        ),
    )


def _find_version_entry(versions: list[dict[str, Any]], version: str) -> dict[str, Any] | None:
    for entry in versions:
        if isinstance(entry, dict) and entry.get("num") == version:
            return entry
    return None


def _entry_created_at(entry: dict[str, Any] | None):
    if not entry:
        return None
    raw = entry.get("created_at")
    if not raw:
        return None
    try:
        return parse_timestamp(raw)
    except ValueError:
        return None


__all__ = ["ECOSYSTEM", "fetch_ref"]
