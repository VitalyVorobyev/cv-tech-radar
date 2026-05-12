from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

from pydantic import BaseModel
from rich.table import Table
from sqlalchemy.orm import Session

from radar.eval.labels import EvalLabel, load_labeled_items
from radar.reports.candidate_queue import collect_candidates
from radar.schemas import RadarRing

DEFAULT_LABELED_ITEMS_PATH = Path("tests/fixtures/labeled_items.yaml")


class EvalRow(BaseModel):
    rank: int
    external_id: str | None
    title: str
    final_score: float
    ring: RadarRing
    label: EvalLabel | None
    false_positive_class: str | None
    note: str


class EvalMetrics(BaseModel):
    candidate_count: int
    labeled_count: int
    relevant_in_top_k: int
    borderline_in_top_k: int
    noise_in_top_k: int
    unlabeled_in_top_k: int
    total_labeled_relevant: int
    total_labeled_noise: int
    precision: float
    recall: float
    false_positive_classes: dict[str, int]
    missing_relevant_external_ids: list[str]


class EvalResult(BaseModel):
    date: date
    limit: int
    fixture_path: str
    metrics: EvalMetrics
    rows: list[EvalRow]


def run_eval(
    session: Session,
    target_date: date,
    *,
    limit: int,
    labeled_items_path: Path = DEFAULT_LABELED_ITEMS_PATH,
) -> EvalResult:
    labeled = load_labeled_items(labeled_items_path)
    by_id = labeled.by_external_id()

    candidates = collect_candidates(session, target_date, limit=limit)

    rows: list[EvalRow] = []
    relevant_in_top_k = 0
    borderline_in_top_k = 0
    noise_in_top_k = 0
    unlabeled_in_top_k = 0
    fp_classes: Counter[str] = Counter()
    seen_relevant_ids: set[str] = set()

    for rank, candidate in enumerate(candidates, start=1):
        ext_id = candidate.external_id
        labeled_item = by_id.get(ext_id) if ext_id else None
        if labeled_item is None:
            unlabeled_in_top_k += 1
            row_label: EvalLabel | None = None
            row_fp_class: str | None = None
            row_note = ""
        else:
            row_label = labeled_item.label
            row_fp_class = labeled_item.false_positive_class
            row_note = labeled_item.note
            if labeled_item.label == EvalLabel.RELEVANT:
                relevant_in_top_k += 1
                seen_relevant_ids.add(labeled_item.external_id)
            elif labeled_item.label == EvalLabel.BORDERLINE:
                borderline_in_top_k += 1
            else:
                noise_in_top_k += 1
                if labeled_item.false_positive_class:
                    fp_classes[labeled_item.false_positive_class] += 1

        rows.append(
            EvalRow(
                rank=rank,
                external_id=ext_id,
                title=candidate.title,
                final_score=candidate.scores.final,
                ring=RadarRing(candidate.ring),
                label=row_label,
                false_positive_class=row_fp_class,
                note=row_note,
            )
        )

    total_relevant = sum(1 for item in labeled.items if item.label == EvalLabel.RELEVANT)
    total_noise = sum(1 for item in labeled.items if item.label == EvalLabel.NOISE)

    decisive = relevant_in_top_k + noise_in_top_k
    precision = relevant_in_top_k / decisive if decisive > 0 else 0.0
    recall = relevant_in_top_k / total_relevant if total_relevant > 0 else 1.0

    missing_relevant = sorted(
        item.external_id
        for item in labeled.items
        if item.label == EvalLabel.RELEVANT and item.external_id not in seen_relevant_ids
    )

    metrics = EvalMetrics(
        candidate_count=len(candidates),
        labeled_count=relevant_in_top_k + borderline_in_top_k + noise_in_top_k,
        relevant_in_top_k=relevant_in_top_k,
        borderline_in_top_k=borderline_in_top_k,
        noise_in_top_k=noise_in_top_k,
        unlabeled_in_top_k=unlabeled_in_top_k,
        total_labeled_relevant=total_relevant,
        total_labeled_noise=total_noise,
        precision=round(precision, 4),
        recall=round(recall, 4),
        false_positive_classes=dict(fp_classes),
        missing_relevant_external_ids=missing_relevant,
    )
    return EvalResult(
        date=target_date,
        limit=limit,
        fixture_path=str(labeled_items_path),
        metrics=metrics,
        rows=rows,
    )


def render_eval_table(result: EvalResult) -> Table:
    table = Table(title=f"Eval top-{result.limit} for {result.date.isoformat()}")
    table.add_column("Rank", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Ring")
    table.add_column("Label")
    table.add_column("FP class")
    table.add_column("Ext ID")
    table.add_column("Title", overflow="fold")
    for row in result.rows:
        table.add_row(
            str(row.rank),
            f"{row.final_score:g}",
            row.ring.value,
            row.label.value if row.label else "—",
            row.false_positive_class or "",
            row.external_id or "",
            row.title,
        )
    return table
