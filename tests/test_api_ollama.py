"""Tests for the Ollama chat + health + manual-draft routes.

These use a real ``OllamaChatClient`` whose underlying ``httpx.Client``
is patched out, so the routes' wiring is exercised end-to-end through
FastAPI without any live Ollama running.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from radar.api import routes
from radar.api.app import create_app


def _copy_real_config(dst: Path) -> Path:
    src = Path("config")
    dst.mkdir(parents=True, exist_ok=True)
    for name in (
        "sources.yaml",
        "topics.yaml",
        "negative_topics.yaml",
        "priority_sources.yaml",
        "scoring.yaml",
        "embeddings.yaml",
    ):
        shutil.copy(src / name, dst / name)
    return dst


@pytest.fixture
def ollama_client(tmp_path):
    config_dir = _copy_real_config(tmp_path / "config")
    db_path = tmp_path / "api.sqlite"
    app = create_app(db_path=db_path, config_dir=config_dir)
    with TestClient(app) as client:
        yield client


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}",
                request=httpx.Request("POST", "http://localhost:11434/api/generate"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict:
        return self._payload


class _FakeHttpxClient:
    """Drop-in for ``httpx.Client`` scoped to a single route module.

    The route does ``with httpx.Client(timeout=3.0) as client: client.get(url)``.
    Patching the route module's ``httpx.Client`` attribute swaps the
    constructor without touching the global ``httpx.Client`` that
    TestClient relies on for ASGI transport.
    """

    def __init__(self, *, on_get):
        self._on_get = on_get

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, **kwargs):  # noqa: ARG002
        return self._on_get(url)


def _patch_generate(monkeypatch, reply: str) -> list[tuple[str, str | None]]:
    """Replace ``OllamaChatClient.generate`` with a stub.

    Returns the list of (prompt, system) tuples the route called the
    client with, so tests can assert on the prompt that reached Ollama.
    """
    captured: list[tuple[str, str | None]] = []

    def fake_generate(self, prompt: str, *, system: str | None = None) -> str:
        captured.append((prompt, system))
        return reply

    monkeypatch.setattr(
        "radar.enrichers.ollama_chat.OllamaChatClient.generate",
        fake_generate,
    )
    # The manual.draft route imports OllamaChatClient by symbol — patch
    # the bound name there too so the stub takes effect regardless of
    # which import path the route uses.
    monkeypatch.setattr(
        "radar.api.routes.manual.OllamaChatClient.generate",
        fake_generate,
    )
    monkeypatch.setattr(
        "radar.api.routes.ollama.OllamaChatClient.generate",
        fake_generate,
    )
    return captured


def _install_fake_httpx(monkeypatch, on_get):
    monkeypatch.setattr(
        "radar.api.routes.ollama.httpx.Client",
        lambda **kwargs: _FakeHttpxClient(on_get=on_get),  # noqa: ARG005
    )


def test_ollama_health_unreachable(ollama_client, monkeypatch):
    """When the local Ollama is down we report ``ok=False`` and the URL,
    not a 5xx — the UI uses this to show a calm 'unreachable' state."""

    def boom(_url):
        raise httpx.ConnectError("no route to host")

    _install_fake_httpx(monkeypatch, boom)

    response = ollama_client.get("/api/ollama/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["base_url"].startswith("http://")
    assert body["error"]


def test_ollama_health_ok(ollama_client, monkeypatch):
    _install_fake_httpx(
        monkeypatch,
        lambda _url: _FakeResponse(payload={"models": []}),
    )
    response = ollama_client.get("/api/ollama/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["chat_model"]
    assert body["embeddings_model"]


def test_ollama_chat_round_trip(ollama_client, monkeypatch):
    captured = _patch_generate(monkeypatch, reply="hi there")

    response = ollama_client.post(
        "/api/ollama/chat",
        json={
            "messages": [
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "Say hi."},
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reply"] == "hi there"
    assert isinstance(body["latency_ms"], int)
    assert body["model"]

    prompt, system = captured[0]
    assert "Say hi." in prompt
    assert "Be concise." in (system or "")
    assert prompt.rstrip().endswith("Assistant:")


def test_ollama_chat_rejects_empty_messages(ollama_client):
    response = ollama_client.post("/api/ollama/chat", json={"messages": []})
    assert response.status_code == 422


def test_ollama_chat_503_when_unreachable(ollama_client, monkeypatch):
    def raise_http_error(self, prompt, *, system=None):  # noqa: ARG001
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(
        "radar.api.routes.ollama.OllamaChatClient.generate",
        raise_http_error,
    )

    response = ollama_client.post(
        "/api/ollama/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 503
    assert "Ollama unreachable" in response.json()["detail"]


def test_manual_draft_parses_clean_json(ollama_client, monkeypatch):
    reply = (
        "{\n"
        '  "title": "Stereo Calibration via Bundle Adjustment",\n'
        '  "abstract": "Subpixel target detection with industrial bundle adjustment.",\n'
        '  "suggested_tracks": ["Calibration & Camera Models", "Made-up Track"],\n'
        '  "suggested_ring": "Watch",\n'
        '  "reason": "Concrete calibration method but no released code.",\n'
        '  "action": "Skim PDF if calibration work resurfaces.",\n'
        '  "uncertain": true\n'
        "}"
    )
    _patch_generate(monkeypatch, reply=reply)

    response = ollama_client.post(
        "/api/items/manual/draft",
        json={"title": "Stereo Calibration", "url": "https://example.test/x"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["suggested_ring"] == "Watch"
    assert body["uncertain"] is True
    # Unknown tracks are filtered out against the configured topics.yaml.
    assert "Calibration & Camera Models" in body["suggested_tracks"]
    assert "Made-up Track" not in body["suggested_tracks"]
    assert "Subpixel" in body["abstract"]
    assert body["raw_response"]


def test_manual_draft_handles_garbage_response(ollama_client, monkeypatch):
    _patch_generate(monkeypatch, reply="I am a chatty model: hello there!")

    response = ollama_client.post(
        "/api/items/manual/draft",
        json={"hint": "found via twitter"},
    )
    assert response.status_code == 200
    body = response.json()
    # Falls back to defaults: Watch, uncertain, empty fields preserved from user.
    assert body["suggested_ring"] == "Watch"
    assert body["uncertain"] is True
    assert body["suggested_tracks"] == []


def test_manual_draft_requires_some_input(ollama_client):
    response = ollama_client.post("/api/items/manual/draft", json={})
    assert response.status_code == 422


def test_manual_draft_503_when_ollama_unreachable(ollama_client, monkeypatch):
    def boom(self, prompt, *, system=None):  # noqa: ARG001
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(
        "radar.api.routes.manual.OllamaChatClient.generate",
        boom,
    )
    response = ollama_client.post(
        "/api/items/manual/draft",
        json={"title": "Something"},
    )
    assert response.status_code == 503
    assert "Ollama unreachable" in response.json()["detail"]


def test_near_duplicates_empty_when_no_embeddings(ollama_client):
    response = ollama_client.get("/api/near-duplicates", params={"date": "2026-05-12"})
    assert response.status_code == 200
    body = response.json()
    assert body["pairs"] == []
    assert body["threshold"] > 0


# Quiet ruff on the unused fixture import — we want it in the namespace
# so the monkeypatched module paths above resolve at import time.
_ = routes
