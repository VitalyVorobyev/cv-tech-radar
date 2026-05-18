"""npm registry release collector.

Polls ``GET https://registry.npmjs.org/{package}`` and reports the
``dist-tags.latest`` version as the ref's current state. Scoped package names
(``@scope/pkg``) are URL-encoded so the ``/`` is not treated as a path segment.
"""

from __future__ import annotations

import httpx

from radar.collectors.ecosystem.base import (
    EcosystemRefResult,
    NormalizedEvent,
    cap_body,
    parse_timestamp,
    request_json,
)

ECOSYSTEM = "npm"


def fetch_ref(client: httpx.Client, ref: str, *, token: str | None = None) -> EcosystemRefResult:
    """Fetch the latest npm release for package ``ref``.

    ``token`` is accepted for a uniform collector signature and ignored. Never
    raises: a 404 yields ``status="not_found"``; any other failure yields
    ``status="error"``.
    """
    # Scoped packages like ``@scope/pkg`` must have the slash percent-encoded.
    encoded_ref = ref.replace("/", "%2f")
    url = f"https://registry.npmjs.org/{encoded_ref}"
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

    dist_tags = payload.get("dist-tags") or {}
    version = dist_tags.get("latest") or ""
    if not version:
        return EcosystemRefResult(status="ok", latest_event=None)

    times = payload.get("time") or {}
    raw_time = times.get(version)
    if not raw_time:
        return EcosystemRefResult(status="ok", latest_event=None)
    try:
        event_date = parse_timestamp(raw_time)
    except ValueError as exc:
        return EcosystemRefResult(status="error", error=f"bad timestamp: {exc}")

    description = payload.get("description") or ""
    version_entry = (payload.get("versions") or {}).get(version) or {}
    return EcosystemRefResult(
        status="ok",
        latest_event=NormalizedEvent(
            version=version,
            event_date=event_date,
            summary=description,
            body=cap_body(description),
            url=f"https://www.npmjs.com/package/{ref}/v/{version}",
            raw_payload=version_entry,
        ),
    )


__all__ = ["ECOSYSTEM", "fetch_ref"]
