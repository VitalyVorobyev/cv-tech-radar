"""Shared contract for ecosystem (package-registry) collectors.

Every ecosystem collector (``github``/``pypi``/``crates``/``npm``) normalizes
its registry's release payload into a :class:`NormalizedEvent` and returns an
:class:`EcosystemRefResult`. The dataclasses here are the frozen interface the
runner dispatches against — keep their shapes stable.

This module also owns the HTTP plumbing: a shared ``httpx`` client that mirrors
``radar.collectors.arxiv._default_client`` (descriptive User-Agent + a
connection-level retrying transport), plus :func:`request_json`, which adds a
per-ecosystem inter-request gate and HTTP 429/5xx retry-with-backoff on top.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

ECOSYSTEM_USER_AGENT = "cv-tech-radar/0.1 (+https://github.com/VitalyVorobyev/cv-tech-radar)"
MAX_BODY_CHARS = 4000

# crates.io's crawler policy asks for roughly one request per second; the other
# registries are happy with a much smaller courtesy gap. Tests patch this dict
# to all-zeros so the suite never actually sleeps.
_MIN_INTERVAL_SECONDS: dict[str, float] = {
    "crates": 1.0,
    "github": 0.25,
    "pypi": 0.25,
    "npm": 0.25,
}

# Last request time per ecosystem, used to enforce ``_MIN_INTERVAL_SECONDS``.
_LAST_REQUEST_AT: dict[str, float] = {}

_MAX_ATTEMPTS = 3
_RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class NormalizedEvent:
    """A single release / version, normalized across registries."""

    version: str  # non-empty release tag / version, e.g. "4.11.0"
    event_date: datetime  # tz-aware UTC, upstream publish time
    summary: str  # one-line human summary
    body: str  # release notes / description, ALREADY capped to MAX_BODY_CHARS
    url: str  # release / version page URL
    raw_payload: dict = field(default_factory=dict)  # release-specific JSON fragment


@dataclass(frozen=True)
class EcosystemRefResult:
    """Outcome of polling one ecosystem ref."""

    status: str  # "ok" | "not_found" | "error"
    latest_event: NormalizedEvent | None = None  # current latest release; None if none / not ok
    error: str = ""


def build_ecosystem_client(timeout: float = 30.0) -> httpx.Client:
    """Return an ``httpx.Client`` configured for ecosystem registry calls.

    Mirrors ``radar.collectors.arxiv._default_client``: a descriptive
    User-Agent (crates.io rejects requests without one) and a transport that
    retries connection-level failures (DNS, TCP reset).
    """
    transport = httpx.HTTPTransport(retries=2)
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        transport=transport,
        headers={"User-Agent": ECOSYSTEM_USER_AGENT},
    )


def cap_body(text: str) -> str:
    """Truncate release-note text to :data:`MAX_BODY_CHARS`."""
    if text is None:
        return ""
    if len(text) <= MAX_BODY_CHARS:
        return text
    return text[:MAX_BODY_CHARS]


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 string into a tz-aware UTC ``datetime``.

    Tolerates a trailing ``Z`` and naive timestamps (assumed UTC).
    """
    if not value:
        msg = "cannot parse an empty timestamp"
        raise ValueError(msg)
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _respect_min_interval(ecosystem: str) -> None:
    """Sleep, if needed, so successive requests to ``ecosystem`` stay polite."""
    min_interval = _MIN_INTERVAL_SECONDS.get(ecosystem, 0.0)
    if min_interval <= 0.0:
        _LAST_REQUEST_AT[ecosystem] = time.monotonic()
        return
    last = _LAST_REQUEST_AT.get(ecosystem)
    now = time.monotonic()
    if last is not None:
        elapsed = now - last
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
    _LAST_REQUEST_AT[ecosystem] = time.monotonic()


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Parse a ``Retry-After`` header (integer-seconds form) if present."""
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw.strip()))
    except (TypeError, ValueError):
        return None


def request_json(
    client: httpx.Client,
    url: str,
    *,
    ecosystem: str,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """GET ``url`` for ``ecosystem``, returning the final response.

    Enforces the per-ecosystem minimum inter-request interval, then retries on
    HTTP 429 and 5xx up to three attempts with exponential backoff (1s, 2s, 4s),
    honoring a ``Retry-After`` header when the server sends one. The caller is
    responsible for inspecting ``response.status_code``.
    """
    response: httpx.Response | None = None
    for attempt in range(_MAX_ATTEMPTS):
        _respect_min_interval(ecosystem)
        response = client.get(url, headers=headers)
        if response.status_code not in _RETRY_STATUS_CODES:
            return response
        if attempt == _MAX_ATTEMPTS - 1:
            return response
        backoff = float(2**attempt)  # 1s, 2s, 4s
        retry_after = _retry_after_seconds(response)
        time.sleep(retry_after if retry_after is not None else backoff)
    # Unreachable (_MAX_ATTEMPTS >= 1) but keeps the type checker happy.
    assert response is not None
    return response


__all__ = [
    "ECOSYSTEM_USER_AGENT",
    "MAX_BODY_CHARS",
    "EcosystemRefResult",
    "NormalizedEvent",
    "build_ecosystem_client",
    "cap_body",
    "parse_timestamp",
    "request_json",
]
