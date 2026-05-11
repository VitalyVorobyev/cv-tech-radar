from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.models import Item, ItemClassification
from radar.schemas import CandidateRecord, CandidateScores, ItemType, RadarRing
from radar.utils import date_bounds, ensure_dir, utc_now


def collect_candidates(
    session: Session,
    target_date: date,
    *,
    limit: int,
) -> list[CandidateRecord]:
    start, end = date_bounds(target_date)
    rows = session.execute(
        select(Item, ItemClassification)
        .join(ItemClassification, ItemClassification.item_id == Item.id)
        .where(Item.published_at >= start, Item.published_at <= end)
        .where(ItemClassification.relevance_score > 0)
        .order_by(ItemClassification.final_score.desc(), Item.title.asc())
        .limit(limit)
    ).all()

    records: list[CandidateRecord] = []
    for item, classification in rows:
        records.append(
            CandidateRecord(
                id=item.id,
                type=ItemType(item.type),
                title=item.title,
                url=item.url,
                pdf_url=item.pdf_url,
                published_at=item.published_at,
                source=item.source_name,
                external_id=item.external_id,
                authors=item.authors_json or [],
                tracks=classification.tracks_json or [],
                ring=RadarRing(classification.recommended_ring),
                scores=CandidateScores(
                    relevance=classification.relevance_score,
                    source_priority=classification.source_priority_score,
                    implementation=classification.implementation_score,
                    attention=classification.attention_score,
                    novelty=classification.novelty_score,
                    negative_penalty=classification.negative_topic_penalty,
                    final=classification.final_score,
                ),
                summary=item.abstract_or_summary,
                pipeline_rationale=classification.rationale,
            )
        )
    return records


def write_candidate_outputs(
    candidates: list[CandidateRecord],
    target_date: date,
    *,
    reports_dir: Path | str = Path("reports/candidates"),
    exports_dir: Path | str = Path("data/exports/candidates"),
) -> tuple[Path, Path]:
    report_path = ensure_dir(Path(reports_dir)) / f"{target_date.isoformat()}.md"
    export_path = ensure_dir(Path(exports_dir)) / f"{target_date.isoformat()}.json"
    report_path.write_text(render_candidate_markdown(candidates, target_date), encoding="utf-8")
    export_payload = {
        "generated_at": utc_now().isoformat(),
        "date": target_date.isoformat(),
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
    }
    export_path.write_text(
        json.dumps(export_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report_path, export_path


def render_candidate_markdown(candidates: list[CandidateRecord], target_date: date) -> str:
    lines = [f"# Candidate Queue - {target_date.isoformat()}", ""]
    if not candidates:
        lines.extend(["No candidates matched the configured threshold.", ""])
        return "\n".join(lines)

    for index, candidate in enumerate(candidates, start=1):
        item_type = candidate.type.value if hasattr(candidate.type, "value") else candidate.type
        ring = candidate.ring.value if hasattr(candidate.ring, "value") else candidate.ring
        lines.extend(
            [
                f"## Candidate {index}: {candidate.title}",
                "",
                f"- Item ID: {candidate.id}",
                f"- Type: {item_type}",
                f"- Source: {candidate.source}",
                f"- URL: {candidate.url}",
                f"- PDF: {candidate.pdf_url or ''}",
                f"- Date: {candidate.published_at.date().isoformat()}",
                f"- Tracks: {', '.join(candidate.tracks) if candidate.tracks else 'None'}",
                f"- Suggested ring: {ring}",
                "- Scores:",
                f"  - relevance: {candidate.scores.relevance:g}",
                f"  - source priority: {candidate.scores.source_priority:g}",
                f"  - implementation: {candidate.scores.implementation:g}",
                f"  - attention: {candidate.scores.attention:g}",
                f"  - novelty: {candidate.scores.novelty:g}",
                f"  - negative penalty: {candidate.scores.negative_penalty:g}",
                f"  - final: {candidate.scores.final:g}",
                "",
                "### Abstract / Summary",
                "",
                candidate.summary or "",
                "",
                "### Pipeline rationale",
                "",
                candidate.pipeline_rationale,
                "",
                "### Claude decision",
                "",
                "TODO",
                "",
            ]
        )
    return "\n".join(lines)
