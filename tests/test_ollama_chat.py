from __future__ import annotations

import json

import httpx
import pytest

from radar.enrichers.ollama_chat import OllamaChatClient


def _client(handler) -> OllamaChatClient:
    return OllamaChatClient(
        model="gemma4:e2b",
        base_url="http://ollama.test",
        timeout_seconds=5,
        temperature=0.0,
        max_tokens=64,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_generate_posts_expected_body_and_returns_response():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/generate"
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"response": "DECISION: yes\nREASON: ok", "done": True})

    client = _client(handler)
    text = client.generate("Hello?", system="be terse")
    assert text == "DECISION: yes\nREASON: ok"
    assert captured["model"] == "gemma4:e2b"
    assert captured["prompt"] == "Hello?"
    assert captured["system"] == "be terse"
    assert captured["stream"] is False
    assert captured["options"]["temperature"] == 0.0
    assert captured["options"]["num_predict"] == 64


def test_generate_omits_system_when_not_provided():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"response": "ok"})

    client = _client(handler)
    assert client.generate("hi") == "ok"
    assert "system" not in captured


def test_generate_raises_when_response_field_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"done": True})

    client = _client(handler)
    with pytest.raises(ValueError):
        client.generate("hi")


def test_generate_raises_for_http_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = _client(handler)
    with pytest.raises(httpx.HTTPStatusError):
        client.generate("hi")


def test_generate_raises_when_budget_exhausted_with_empty_response():
    from radar.enrichers.ollama_chat import OllamaChatBudgetExhausted

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "", "done": True, "done_reason": "length"})

    client = _client(handler)
    with pytest.raises(OllamaChatBudgetExhausted) as exc_info:
        client.generate("hi")
    assert "max_tokens" in str(exc_info.value)


def test_generate_returns_truncated_response_when_partial_content_present():
    """`done_reason='length'` is fine when there IS visible content — the
    parser may still recover a DECISION line from a truncated response."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": "DECISION: yes\nREAS",
                "done": True,
                "done_reason": "length",
            },
        )

    client = _client(handler)
    assert client.generate("hi") == "DECISION: yes\nREAS"
