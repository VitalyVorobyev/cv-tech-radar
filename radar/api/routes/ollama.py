"""Generic Ollama chat surface exposed to the UI.

The existing ``OllamaChatClient`` only knows how to call ``/api/generate``
with a single ``prompt`` string. To support a chat-style conversation we
fold the message list into a single prompt with role prefixes — the model
gets the same context shape an OpenAI ``messages`` array would carry.

Streaming is intentionally not implemented in v1: the UI uses a single
POST and renders the full reply when it arrives. If the user wants
streaming later we add a SSE endpoint without breaking this contract.
"""

from __future__ import annotations

import time
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from radar.api.deps import get_config
from radar.enrichers.ollama_chat import OllamaChatBudgetExhausted, OllamaChatClient
from radar.schemas import AppConfig, ChatSettings

router = APIRouter(prefix="/ollama", tags=["ollama"])


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(min_length=1)
    model: str | None = None
    system: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)


class ChatResponse(BaseModel):
    reply: str
    model: str
    latency_ms: int


class OllamaHealthResponse(BaseModel):
    ok: bool
    base_url: str
    chat_model: str
    chat_enabled: bool
    embeddings_model: str
    embeddings_enabled: bool
    error: str | None = None


def _build_prompt(messages: list[ChatMessage]) -> tuple[str, str | None]:
    """Fold the message list into one prompt + an optional system message.

    The ``OllamaChatClient.generate`` API takes ``prompt`` and ``system``;
    we keep any explicit system message separate and concatenate the rest
    with ``User:`` / ``Assistant:`` prefixes so the model can pick up the
    turn structure.
    """
    system_parts: list[str] = []
    body_parts: list[str] = []
    for message in messages:
        if message.role == "system":
            system_parts.append(message.content.strip())
        elif message.role == "user":
            body_parts.append(f"User: {message.content.strip()}")
        else:
            body_parts.append(f"Assistant: {message.content.strip()}")
    # Encourage the model to take the next turn explicitly.
    if not body_parts or not body_parts[-1].startswith("Assistant:"):
        body_parts.append("Assistant:")
    body = "\n\n".join(body_parts)
    system = "\n\n".join(system_parts) if system_parts else None
    return body, system


def _build_client(settings: ChatSettings, payload: ChatRequest) -> OllamaChatClient:
    return OllamaChatClient(
        model=payload.model or settings.model,
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
        temperature=payload.temperature
        if payload.temperature is not None
        else settings.temperature,
        max_tokens=payload.max_tokens if payload.max_tokens is not None else settings.max_tokens,
    )


@router.get("/health", response_model=OllamaHealthResponse)
def get_ollama_health(
    config: Annotated[AppConfig, Depends(get_config)],
) -> OllamaHealthResponse:
    """Ping Ollama's ``/api/tags`` endpoint to confirm reachability.

    Returns ``ok=False`` rather than raising so the UI can render a calm
    "Ollama unreachable" message instead of a stack trace.
    """
    chat = config.embeddings.chat
    embeddings = config.embeddings.embeddings
    base = chat.base_url.rstrip("/")
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(f"{base}/api/tags")
            response.raise_for_status()
        return OllamaHealthResponse(
            ok=True,
            base_url=base,
            chat_model=chat.model,
            chat_enabled=chat.enabled,
            embeddings_model=embeddings.model,
            embeddings_enabled=embeddings.enabled,
        )
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        return OllamaHealthResponse(
            ok=False,
            base_url=base,
            chat_model=chat.model,
            chat_enabled=chat.enabled,
            embeddings_model=embeddings.model,
            embeddings_enabled=embeddings.enabled,
            error=str(exc),
        )


@router.post("/chat", response_model=ChatResponse)
def post_ollama_chat(
    payload: ChatRequest,
    config: Annotated[AppConfig, Depends(get_config)],
) -> ChatResponse:
    settings = config.embeddings.chat
    prompt, derived_system = _build_prompt(payload.messages)
    system = payload.system or derived_system
    client = _build_client(settings, payload)

    started = time.perf_counter()
    try:
        reply = client.generate(prompt, system=system)
    except OllamaChatBudgetExhausted as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Ollama unreachable at {settings.base_url}: {exc}",
        ) from exc
    latency_ms = int((time.perf_counter() - started) * 1000)
    return ChatResponse(reply=reply, model=client.model, latency_ms=latency_ms)
