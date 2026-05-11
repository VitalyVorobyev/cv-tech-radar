from __future__ import annotations

import httpx

from radar.enrichers.ollama import OllamaEmbeddingClient


def test_ollama_embedding_client_with_mocked_http():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embeddings"
        payload = json_from_request(request)
        assert payload["model"] == "embeddinggemma:latest"
        assert payload["prompt"] == "camera calibration"
        return httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})

    client = OllamaEmbeddingClient(
        model="embeddinggemma:latest",
        base_url="http://ollama.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.embed("camera calibration") == [0.1, 0.2, 0.3]


def json_from_request(request: httpx.Request):
    import json

    return json.loads(request.content.decode("utf-8"))
