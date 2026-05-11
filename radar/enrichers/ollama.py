from __future__ import annotations

import httpx


class OllamaEmbeddingClient:
    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://localhost:11434",
        timeout_seconds: int = 30,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client

    def embed(self, text: str) -> list[float]:
        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        close_client = self._client is None
        try:
            response = client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            if close_client:
                client.close()
        embedding = payload.get("embedding")
        has_numeric_embedding = isinstance(embedding, list) and all(
            isinstance(value, int | float) for value in embedding
        )
        if not has_numeric_embedding:
            msg = "Ollama embedding response did not contain a numeric embedding list"
            raise ValueError(msg)
        return [float(value) for value in embedding]
