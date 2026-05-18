"""Offline tests for the four ecosystem collectors.

Each collector is fed an ``httpx.Client`` backed by a ``MockTransport`` that
returns canned, minimal-but-realistic JSON. No real network is touched. The
per-ecosystem inter-request gate is zeroed so the suite stays fast.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from radar.collectors.ecosystem import base as ecosystem_base
from radar.collectors.ecosystem import crates, github, npm, pypi


@pytest.fixture(autouse=True)
def _no_rate_limit_sleep(monkeypatch):
    """Zero the inter-request interval and patch out sleeping entirely."""
    monkeypatch.setattr(
        ecosystem_base,
        "_MIN_INTERVAL_SECONDS",
        dict.fromkeys(("crates", "github", "pypi", "npm"), 0.0),
    )
    monkeypatch.setattr(ecosystem_base.time, "sleep", lambda _seconds: None)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- GitHub -----------------------------------------------------------------

_GITHUB_RELEASES = [
    {
        "tag_name": "4.11.0",
        "name": "OpenCV 4.11.0",
        "body": "ArUco improvements and calib3d fixes.",
        "html_url": "https://github.com/opencv/opencv/releases/tag/4.11.0",
        "published_at": "2026-02-01T10:00:00Z",
        "draft": False,
        "prerelease": False,
    },
    {
        "tag_name": "4.12.0-rc1",
        "name": "OpenCV 4.12.0 RC1",
        "body": "Release candidate.",
        "html_url": "https://github.com/opencv/opencv/releases/tag/4.12.0-rc1",
        "published_at": "2026-03-01T10:00:00Z",
        "draft": False,
        "prerelease": True,
    },
    {
        "tag_name": "4.10.0",
        "name": "OpenCV 4.10.0",
        "body": "Older release.",
        "html_url": "https://github.com/opencv/opencv/releases/tag/4.10.0",
        "published_at": "2025-12-01T10:00:00Z",
        "draft": False,
        "prerelease": False,
    },
]


def test_github_fetch_ref_picks_latest_stable_release():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/opencv/opencv/releases"
        assert request.url.params["per_page"] == "10"
        return httpx.Response(200, json=_GITHUB_RELEASES)

    result = github.fetch_ref(_client(handler), "opencv/opencv")
    assert result.status == "ok"
    assert result.latest_event is not None
    # The newest non-draft, non-prerelease release wins (the RC is skipped).
    assert result.latest_event.version == "4.11.0"
    assert result.latest_event.event_date == datetime(2026, 2, 1, 10, 0, tzinfo=UTC)
    assert result.latest_event.url.endswith("/tag/4.11.0")
    assert result.latest_event.summary == "OpenCV 4.11.0"


def test_github_fetch_ref_sends_authorization_header_when_token_given():
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=_GITHUB_RELEASES)

    github.fetch_ref(_client(handler), "opencv/opencv", token="secret-token")
    assert seen["auth"] == "Bearer secret-token"


def test_github_fetch_ref_empty_release_list_is_ok_with_no_event():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    result = github.fetch_ref(_client(handler), "owner/empty")
    assert result.status == "ok"
    assert result.latest_event is None


def test_github_fetch_ref_404_is_not_found():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    result = github.fetch_ref(_client(handler), "owner/missing")
    assert result.status == "not_found"
    assert result.latest_event is None


# --- PyPI -------------------------------------------------------------------

_PYPI_PAYLOAD = {
    "info": {"version": "2.6.0", "summary": "Differentiable computer vision in PyTorch."},
    "releases": {
        "2.6.0": [
            {
                "filename": "kornia-2.6.0-py3-none-any.whl",
                "upload_time_iso_8601": "2026-04-10T08:30:00Z",
            }
        ],
        "2.5.0": [],
    },
}


def test_pypi_fetch_ref_reports_info_version():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/pypi/kornia/json"
        return httpx.Response(200, json=_PYPI_PAYLOAD)

    result = pypi.fetch_ref(_client(handler), "kornia")
    assert result.status == "ok"
    assert result.latest_event is not None
    assert result.latest_event.version == "2.6.0"
    assert result.latest_event.event_date == datetime(2026, 4, 10, 8, 30, tzinfo=UTC)
    assert result.latest_event.url == "https://pypi.org/project/kornia/2.6.0/"


def test_pypi_fetch_ref_404_is_not_found():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    result = pypi.fetch_ref(_client(handler), "no-such-pkg")
    assert result.status == "not_found"


def test_pypi_fetch_ref_version_with_no_files_yields_no_event():
    payload = {
        "info": {"version": "1.0.0", "summary": "Empty release."},
        "releases": {"1.0.0": []},
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    result = pypi.fetch_ref(_client(handler), "emptypkg")
    assert result.status == "ok"
    assert result.latest_event is None


# --- crates.io --------------------------------------------------------------

_CRATES_PAYLOAD = {
    "crate": {
        "max_stable_version": "0.33.2",
        "newest_version": "0.34.0-beta",
        "max_version": "0.34.0-beta",
        "description": "Linear algebra library for the Rust programming language.",
    },
    "versions": [
        {"num": "0.34.0-beta", "created_at": "2026-05-01T12:00:00Z"},
        {"num": "0.33.2", "created_at": "2026-03-15T09:00:00Z"},
    ],
}


def test_crates_fetch_ref_reports_max_stable_version():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/crates/nalgebra"
        return httpx.Response(200, json=_CRATES_PAYLOAD)

    result = crates.fetch_ref(_client(handler), "nalgebra")
    assert result.status == "ok"
    assert result.latest_event is not None
    assert result.latest_event.version == "0.33.2"
    assert result.latest_event.event_date == datetime(2026, 3, 15, 9, 0, tzinfo=UTC)
    assert result.latest_event.url == "https://crates.io/crates/nalgebra/0.33.2"


def test_crates_fetch_ref_404_is_not_found():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"errors": [{"detail": "Not Found"}]})

    result = crates.fetch_ref(_client(handler), "no-such-crate")
    assert result.status == "not_found"


# --- npm --------------------------------------------------------------------

_NPM_PAYLOAD = {
    "dist-tags": {"latest": "7.1.0"},
    "description": "Next generation frontend tooling.",
    "time": {
        "7.0.0": "2026-01-01T00:00:00.000Z",
        "7.1.0": "2026-04-20T15:45:00.000Z",
    },
    "versions": {"7.1.0": {"name": "vite", "version": "7.1.0"}},
}


def test_npm_fetch_ref_reports_dist_tag_latest():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/vite"
        return httpx.Response(200, json=_NPM_PAYLOAD)

    result = npm.fetch_ref(_client(handler), "vite")
    assert result.status == "ok"
    assert result.latest_event is not None
    assert result.latest_event.version == "7.1.0"
    assert result.latest_event.event_date == datetime(2026, 4, 20, 15, 45, tzinfo=UTC)
    assert result.latest_event.url == "https://www.npmjs.com/package/vite/v/7.1.0"


def test_npm_fetch_ref_url_encodes_scoped_package():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["raw_path"] = request.url.raw_path.decode()
        return httpx.Response(200, json=_NPM_PAYLOAD)

    result = npm.fetch_ref(_client(handler), "@scope/pkg")
    assert result.status == "ok"
    # The "/" in the scoped name must be percent-encoded in the request path.
    assert "%2f" in seen["raw_path"].lower()


def test_npm_fetch_ref_404_is_not_found():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "Not found"})

    result = npm.fetch_ref(_client(handler), "no-such-package")
    assert result.status == "not_found"


# --- shared base behavior ---------------------------------------------------


def test_request_json_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(ecosystem_base.time, "sleep", lambda _seconds: None)
    attempts: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 2:
            return httpx.Response(429, json={"message": "slow down"})
        return httpx.Response(200, json={"ok": True})

    response = ecosystem_base.request_json(_client(handler), "https://x.test/", ecosystem="github")
    assert response.status_code == 200
    assert len(attempts) == 2


def test_fetch_ref_never_raises_on_network_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    result = github.fetch_ref(_client(handler), "owner/repo")
    assert result.status == "error"
    assert result.error
