from __future__ import annotations

import httpx


class OllamaChatBudgetExhausted(RuntimeError):
    """Raised when Ollama returned an empty response because the model burned
    its entire ``num_predict`` budget on internal reasoning (`done_reason ==
    "length"` with `response == ""`). The fix is to raise the configured
    ``chat.max_tokens`` so the model has room for visible output after
    reasoning."""


class OllamaChatClient:
    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://localhost:11434",
        timeout_seconds: int = 60,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = client

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        close_client = self._client is None
        try:
            body: dict = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            }
            if system:
                body["system"] = system
            response = client.post(f"{self.base_url}/api/generate", json=body)
            response.raise_for_status()
            payload = response.json()
        finally:
            if close_client:
                client.close()
        text = payload.get("response")
        if not isinstance(text, str):
            msg = "Ollama chat response did not contain a string 'response' field"
            raise ValueError(msg)
        if text == "" and payload.get("done_reason") == "length":
            msg = (
                f"Ollama returned an empty response with done_reason='length' "
                f"(model={self.model}, num_predict={self.max_tokens}). The model "
                f"likely consumed the budget on internal reasoning before producing "
                f"visible output — raise chat.max_tokens."
            )
            raise OllamaChatBudgetExhausted(msg)
        return text
