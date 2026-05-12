from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.enrichers.ollama_chat import OllamaChatClient
from radar.models import Item, ItemClassification, ItemLLMJudgment
from radar.schemas import ChatSettings
from radar.utils import date_bounds

JudgmentOutcome = Literal["yes", "no", "unknown", "skipped", "failed"]
ProgressCallback = Callable[[int, int, Item, JudgmentOutcome], None]

SYSTEM_PROMPT = (
    "You are a strict reviewer for a private computer-vision technology radar "
    "focused on industrial computer vision.\n\n"
    "IN SCOPE: camera calibration, target detection, 3D geometry and "
    "reconstruction, 3D sensors and depth, industrial vision inspection, "
    "robot guidance, object tracking for industrial use, edge AI deployment "
    "for vision, open-source CV tooling, sensors and cameras and standards, "
    "datasets and benchmarks for industrial CV.\n\n"
    "OUT OF SCOPE: medical imaging, autonomous-driving stacks, generative "
    "image or video editing, broad multimodal benchmarks, foundation-model "
    "semantic search, human pose / gaze / egocentric, biometric search, "
    "document parsing, text-to-CAD generation, consumer smartphone imaging.\n\n"
    "Answer in EXACTLY this format and nothing else:\n"
    "DECISION: yes\n"
    "REASON: <one short sentence>\n\n"
    "or\n\n"
    "DECISION: no\n"
    "REASON: <one short sentence>\n"
)


DECISION_YES = "yes"
DECISION_NO = "no"
DECISION_UNKNOWN = "unknown"


@dataclass(frozen=True)
class RelevanceJudgment:
    decision: str
    reason: str
    raw_response: str


@dataclass(frozen=True)
class JudgmentSummary:
    total: int
    judged: int
    skipped: int
    failed: int
    yes_count: int
    no_count: int
    unknown_count: int


def build_user_prompt(item: Item) -> str:
    title = (item.title or "").strip()
    abstract = (item.abstract_or_summary or "").strip()
    if abstract:
        return f"Title: {title}\n\nAbstract:\n{abstract}\n"
    return f"Title: {title}\n"


_DECISION_RE = re.compile(r"^\s*DECISION\s*:\s*(yes|no)\b", re.IGNORECASE | re.MULTILINE)
_REASON_RE = re.compile(r"^\s*REASON\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def parse_judgment(raw_response: str) -> RelevanceJudgment:
    decision_match = _DECISION_RE.search(raw_response or "")
    reason_match = _REASON_RE.search(raw_response or "")
    if decision_match is None:
        return RelevanceJudgment(
            decision=DECISION_UNKNOWN,
            reason="",
            raw_response=raw_response or "",
        )
    decision = decision_match.group(1).lower()
    reason = reason_match.group(1).strip() if reason_match else ""
    return RelevanceJudgment(
        decision=decision,
        reason=reason,
        raw_response=raw_response or "",
    )


def check_relevance_for_date(
    session: Session,
    settings: ChatSettings,
    target_date: date,
    *,
    client: OllamaChatClient | None = None,
    limit: int | None = None,
    on_progress: ProgressCallback | None = None,
    rejudge: bool = False,
) -> JudgmentSummary:
    start, end = date_bounds(target_date)
    rows = list(
        session.execute(
            select(Item, ItemClassification)
            .join(ItemClassification, ItemClassification.item_id == Item.id)
            .where(Item.published_at >= start, Item.published_at <= end)
            .where(ItemClassification.relevance_score > 0)
            .order_by(ItemClassification.final_score.desc(), Item.title.asc())
        ).all()
    )
    if limit is not None:
        rows = rows[:limit]

    if client is None:
        client = OllamaChatClient(
            model=settings.model,
            base_url=settings.base_url,
            timeout_seconds=settings.timeout_seconds,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )

    judged = skipped = failed = 0
    yes_count = no_count = unknown_count = 0
    total = len(rows)

    for index, (item, _classification) in enumerate(rows, start=1):
        existing = session.scalar(
            select(ItemLLMJudgment).where(
                ItemLLMJudgment.item_id == item.id,
                ItemLLMJudgment.model == settings.model,
            )
        )
        if existing is not None and not rejudge:
            skipped += 1
            if on_progress is not None:
                on_progress(index, total, item, "skipped")
            continue
        if existing is not None:
            session.delete(existing)
            session.flush()
        try:
            raw = client.generate(build_user_prompt(item), system=SYSTEM_PROMPT)
        except Exception:
            failed += 1
            if on_progress is not None:
                on_progress(index, total, item, "failed")
            continue
        judgment = parse_judgment(raw)
        session.add(
            ItemLLMJudgment(
                item_id=item.id,
                model=settings.model,
                decision=judgment.decision,
                reason=judgment.reason,
                raw_response=judgment.raw_response,
            )
        )
        judged += 1
        outcome: JudgmentOutcome
        if judgment.decision == DECISION_YES:
            yes_count += 1
            outcome = "yes"
        elif judgment.decision == DECISION_NO:
            no_count += 1
            outcome = "no"
        else:
            unknown_count += 1
            outcome = "unknown"
        if on_progress is not None:
            on_progress(index, total, item, outcome)

    session.flush()
    return JudgmentSummary(
        total=total,
        judged=judged,
        skipped=skipped,
        failed=failed,
        yes_count=yes_count,
        no_count=no_count,
        unknown_count=unknown_count,
    )
