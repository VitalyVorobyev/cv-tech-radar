"""Manually add a paper to the radar.

The user supplies the fields they have on hand (URL, title, abstract,
authors, published date). The endpoint reuses ``store_normalized_item``
so the dedup + raw-payload contract is preserved, then classifies the
new item inline so it appears in the queue immediately.

A second endpoint, ``POST /api/items/manual/draft``, asks the local
Ollama model to fill the gaps (suggested tracks, ring, reason) given
whatever the user has so far. The user then reviews/edits in the UI and
submits to the main ``POST /api/items/manual`` endpoint.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.api.deps import get_config, get_session
from radar.collectors.arxiv import store_normalized_item
from radar.enrichers.ollama_chat import OllamaChatBudgetExhausted, OllamaChatClient
from radar.filters.keyword_filter import classify_item, upsert_classification
from radar.models import Item, Source
from radar.schemas import AppConfig, ItemType, NormalizedItem, RadarRing

router = APIRouter(prefix="/items", tags=["items"])

MANUAL_SOURCE_KEY = "manual"
MANUAL_SOURCE_NAME = "Manual"


class ManualItemPayload(BaseModel):
    """Fields the user fills in by hand. URL + title + published date are
    mandatory; everything else is optional so the form stays lightweight."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1)
    abstract: str = ""
    published_at: datetime
    authors: list[str] = Field(default_factory=list)
    pdf_url: str | None = None
    doi: str | None = None
    external_id: str | None = None
    item_type: ItemType = ItemType.PAPER


class ManualItemResponse(BaseModel):
    item_id: int
    created: bool
    tracks: list[str]
    positive_keywords: list[str]
    recommended_ring: str
    final_score: float


def _ensure_manual_source(session: Session) -> Source:
    """Return the bootstrap manual source row, creating it if absent.

    ``get_engine_dep`` already calls ``ensure_sources`` on first request,
    so the row is normally present. This second guard makes the route
    robust against an empty DB that skipped startup ensure.
    """
    source = session.scalar(select(Source).where(Source.key == MANUAL_SOURCE_KEY))
    if source is not None:
        return source
    source = Source(
        key=MANUAL_SOURCE_KEY,
        name=MANUAL_SOURCE_NAME,
        kind="manual",
        url="https://manual.cv-radar.local/",
        enabled=True,
        priority=1,
        notes="Permanent source row for papers added by hand via the UI.",
    )
    session.add(source)
    session.flush()
    return source


@router.post("/manual", response_model=ManualItemResponse, status_code=201)
def add_manual_item(
    payload: ManualItemPayload,
    session: Annotated[Session, Depends(get_session)],
    config: Annotated[AppConfig, Depends(get_config)],
) -> ManualItemResponse:
    source = _ensure_manual_source(session)

    normalized = NormalizedItem(
        type=payload.item_type,
        title=payload.title.strip(),
        abstract_or_summary=payload.abstract.strip(),
        url=payload.url.strip(),
        pdf_url=payload.pdf_url,
        published_at=payload.published_at,
        source_name=source.name,
        external_id=payload.external_id or payload.url.strip(),
        doi=payload.doi,
        authors=[author.strip() for author in payload.authors if author.strip()],
    )
    raw_payload = {
        "source": "manual",
        "submitted_at": datetime.now(payload.published_at.tzinfo).isoformat()
        if payload.published_at.tzinfo
        else datetime.utcnow().isoformat(),
        "payload": payload.model_dump(mode="json"),
    }

    created = store_normalized_item(
        session=session,
        source=source,
        normalized=normalized,
        raw_payload=raw_payload,
    )
    session.flush()

    item = session.scalar(select(Item).where(Item.url == normalized.url))
    if item is None:
        raise HTTPException(status_code=500, detail="manual item write did not persist")

    classification = classify_item(item, config=config, source=source)
    upsert_classification(session, item, classification)

    return ManualItemResponse(
        item_id=item.id,
        created=created,
        tracks=classification.tracks,
        positive_keywords=classification.positive_keywords,
        recommended_ring=classification.recommended_ring.value,
        final_score=classification.final_score,
    )


class ManualDraftRequest(BaseModel):
    """What the user has so far. All fields are optional; the assistant
    fills in the gaps. At least one of ``url``, ``title``, ``abstract`` or
    ``hint`` must be present."""

    model_config = ConfigDict(extra="forbid")

    url: str | None = None
    title: str | None = None
    abstract: str | None = None
    hint: str | None = Field(
        default=None,
        description=(
            "Free-text context the user wants the model to use (e.g. 'short notes from skim')."
        ),
    )

    def is_empty(self) -> bool:
        return not any((self.url, self.title, self.abstract, self.hint))


class ManualDraftResponse(BaseModel):
    title: str = ""
    abstract: str = ""
    suggested_tracks: list[str] = Field(default_factory=list)
    suggested_ring: str = "Watch"
    reason: str = ""
    action: str = ""
    uncertain: bool = True
    model: str
    latency_ms: int
    raw_response: str


_DRAFT_SYSTEM = """You are an assistant that helps a computer-vision engineer
curate a private technology radar focused on calibration, target detection,
3D geometry, 3D sensors, robot guidance, industrial vision inspection, object
tracking, edge AI deployment, sensors/cameras/standards, synthetic data, and
datasets/benchmarks. Avoid promoting items based only on famous authors or
large claims. Prefer practical, industrially relevant work.

You must respond with a single JSON object only. No prose before or after. Schema:

{
  "title": "string",
  "abstract": "string (one-paragraph technical summary you wrote yourself, 60-120 words)",
  "suggested_tracks": ["string", ...]  // pick 0-3 from the user's provided track list,
  "suggested_ring": "Use|Prototype|Evaluate|Watch|Ignore",
  "reason": "string (one or two sentences, the WHY for the ring choice)",
  "action": "string (one sentence next-step the user could take)",
  "uncertain": true|false
}

Be skeptical. Default to Watch or Ignore unless there is clear industrial-relevance evidence \
(code, dataset, deployment numbers). Use 'uncertain: true' when you had to guess."""


def _draft_user_prompt(payload: ManualDraftRequest, tracks: list[str]) -> str:
    track_list = ", ".join(tracks) if tracks else "(no tracks configured)"
    lines = [
        f"Available radar tracks: {track_list}",
        "",
        "Information the user has so far:",
        f"- URL: {payload.url or '(not provided)'}",
        f"- Title: {payload.title or '(not provided)'}",
        f"- Abstract: {payload.abstract or '(not provided)'}",
    ]
    if payload.hint:
        lines.extend(["", f"User's note: {payload.hint}"])
    lines.extend(
        [
            "",
            "Return the JSON object now. No code fences. No commentary.",
        ]
    )
    return "\n".join(lines)


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict | None:
    """Best-effort JSON extraction.

    Small local models occasionally wrap output in code fences, prose, or
    repeat the prompt before answering. We pull out the first balanced
    ``{...}`` block and try to parse it.
    """
    text = text.strip()
    if not text:
        return None
    match = _JSON_BLOCK_RE.search(text)
    if match is None:
        return None
    blob = match.group(0)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _coerce_ring(value) -> str:
    try:
        return RadarRing(value).value
    except (ValueError, KeyError, TypeError):
        return RadarRing.WATCH.value


@router.post("/manual/draft", response_model=ManualDraftResponse)
def draft_manual_item(
    payload: ManualDraftRequest,
    config: Annotated[AppConfig, Depends(get_config)],
) -> ManualDraftResponse:
    if payload.is_empty():
        raise HTTPException(
            status_code=422,
            detail="at least one of url, title, abstract, hint is required",
        )

    chat_settings = config.embeddings.chat
    client = OllamaChatClient(
        model=chat_settings.model,
        base_url=chat_settings.base_url,
        timeout_seconds=chat_settings.timeout_seconds,
        temperature=chat_settings.temperature,
        max_tokens=chat_settings.max_tokens,
    )
    tracks = [track.name for track in config.topics.tracks]

    import time

    started = time.perf_counter()
    try:
        raw = client.generate(_draft_user_prompt(payload, tracks), system=_DRAFT_SYSTEM)
    except OllamaChatBudgetExhausted as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Ollama unreachable at {chat_settings.base_url}: {exc}",
        ) from exc
    latency_ms = int((time.perf_counter() - started) * 1000)

    parsed = _extract_json(raw) or {}
    allowed_tracks = {track.lower(): track for track in tracks}
    suggested = [
        allowed_tracks[t.lower()]
        for t in parsed.get("suggested_tracks", [])
        if isinstance(t, str) and t.lower() in allowed_tracks
    ]

    return ManualDraftResponse(
        title=str(parsed.get("title", "") or payload.title or "").strip(),
        abstract=str(parsed.get("abstract", "") or payload.abstract or "").strip(),
        suggested_tracks=suggested,
        suggested_ring=_coerce_ring(parsed.get("suggested_ring", "Watch")),
        reason=str(parsed.get("reason", "") or "").strip(),
        action=str(parsed.get("action", "") or "").strip(),
        uncertain=bool(parsed.get("uncertain", True)) if parsed else True,
        model=client.model,
        latency_ms=latency_ms,
        raw_response=raw,
    )
