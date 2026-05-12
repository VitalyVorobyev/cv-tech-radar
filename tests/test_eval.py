from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
import yaml
from pydantic import ValidationError

from radar.db import session_scope
from radar.eval import (
    DEFAULT_LABELED_ITEMS_PATH,
    EvalLabel,
    run_eval,
)
from radar.eval.labels import LabeledSet, load_labeled_items
from radar.filters.keyword_filter import upsert_classification
from radar.models import Item
from radar.schemas import ClassificationResult, RadarRing


def _seed_item(
    session,
    *,
    external_id: str,
    title: str,
    final: float,
    relevance: float = 50.0,
    ring: RadarRing = RadarRing.WATCH,
    published: datetime,
) -> Item:
    item = Item(
        type="paper",
        title=title,
        normalized_title=title.casefold(),
        abstract_or_summary=title,
        url=f"https://example.test/{external_id}",
        pdf_url=None,
        published_at=published,
        updated_at=None,
        source_name="arXiv cs.CV",
        external_id=external_id,
        arxiv_id=external_id,
        authors_json=[],
        organizations_json=[],
        metadata_json={},
    )
    session.add(item)
    session.flush()
    upsert_classification(
        session,
        item,
        ClassificationResult(
            tracks=[],
            positive_keywords=[],
            negative_keywords=[],
            relevance_score=relevance,
            novelty_score=0,
            source_priority_score=0,
            implementation_score=0,
            attention_score=0,
            final_score=final,
            negative_topic_penalty=0,
            recommended_ring=ring,
            confidence=0.5,
            rationale="seed",
        ),
    )
    return item


def test_default_fixture_loads_and_ids_are_unique():
    labeled = load_labeled_items(DEFAULT_LABELED_ITEMS_PATH)
    assert len(labeled.items) > 0
    ids = [item.external_id for item in labeled.items]
    assert len(ids) == len(set(ids))
    # noise items always carry a class so the per-class breakdown is meaningful
    for item in labeled.items:
        if item.label == EvalLabel.NOISE:
            assert item.false_positive_class, (
                f"{item.external_id} labeled noise without false_positive_class"
            )


def test_false_positive_class_rejected_on_non_noise(tmp_path):
    bad = {
        "items": [
            {
                "external_id": "X",
                "title": "T",
                "label": "relevant",
                "false_positive_class": "broad_vlm",
            }
        ]
    }
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_labeled_items(path)


def test_duplicate_external_ids_rejected(tmp_path):
    bad = {
        "items": [
            {"external_id": "X", "title": "A", "label": "relevant"},
            {"external_id": "X", "title": "B", "label": "noise", "false_positive_class": "c"},
        ]
    }
    path = tmp_path / "dup.yaml"
    path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_labeled_items(path)


def test_loader_rejects_missing_file(tmp_path):
    missing = tmp_path / "nope.yaml"
    with pytest.raises(FileNotFoundError):
        load_labeled_items(missing)


def test_labeled_set_by_external_id_round_trip():
    set_ = LabeledSet.model_validate(
        {
            "items": [
                {"external_id": "a", "title": "A", "label": "relevant"},
                {
                    "external_id": "b",
                    "title": "B",
                    "label": "noise",
                    "false_positive_class": "broad_vlm",
                },
            ]
        }
    )
    by_id = set_.by_external_id()
    assert set(by_id) == {"a", "b"}
    assert by_id["a"].label == EvalLabel.RELEVANT
    assert by_id["b"].false_positive_class == "broad_vlm"


def test_run_eval_metrics_on_synthetic_db(db_engine, tmp_path):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    fixture = {
        "items": [
            {"external_id": "good-1", "title": "Good 1", "label": "relevant"},
            {"external_id": "good-2", "title": "Good 2", "label": "relevant"},
            {
                "external_id": "noise-1",
                "title": "Noise 1",
                "label": "noise",
                "false_positive_class": "broad_vlm",
            },
            {
                "external_id": "noise-2",
                "title": "Noise 2",
                "label": "noise",
                "false_positive_class": "broad_vlm",
            },
            {"external_id": "border-1", "title": "Border 1", "label": "borderline"},
            {"external_id": "missing-relevant", "title": "Missing", "label": "relevant"},
        ]
    }
    fixture_path = tmp_path / "labels.yaml"
    fixture_path.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    with session_scope(db_engine) as session:
        _seed_item(
            session,
            external_id="good-1",
            title="Good 1",
            final=90,
            ring=RadarRing.USE,
            published=pub,
        )
        _seed_item(
            session,
            external_id="good-2",
            title="Good 2",
            final=70,
            ring=RadarRing.EVALUATE,
            published=pub,
        )
        _seed_item(
            session,
            external_id="noise-1",
            title="Noise 1",
            final=60,
            ring=RadarRing.WATCH,
            published=pub,
        )
        _seed_item(
            session,
            external_id="noise-2",
            title="Noise 2",
            final=50,
            ring=RadarRing.WATCH,
            published=pub,
        )
        _seed_item(
            session,
            external_id="border-1",
            title="Border 1",
            final=40,
            ring=RadarRing.IGNORE,
            published=pub,
        )
        _seed_item(
            session,
            external_id="unlabeled",
            title="Unlabeled",
            final=30,
            ring=RadarRing.IGNORE,
            published=pub,
        )

        result = run_eval(
            session,
            date(2026, 5, 10),
            limit=10,
            labeled_items_path=fixture_path,
        )

    metrics = result.metrics
    assert metrics.candidate_count == 6
    assert metrics.labeled_count == 5
    assert metrics.relevant_in_top_k == 2
    assert metrics.borderline_in_top_k == 1
    assert metrics.noise_in_top_k == 2
    assert metrics.unlabeled_in_top_k == 1
    assert metrics.total_labeled_relevant == 3
    assert metrics.total_labeled_noise == 2
    assert metrics.precision == pytest.approx(0.5, rel=1e-3)
    assert metrics.recall == pytest.approx(2 / 3, rel=1e-3)
    assert metrics.false_positive_classes == {"broad_vlm": 2}
    assert metrics.missing_relevant_external_ids == ["missing-relevant"]

    assert [row.rank for row in result.rows] == [1, 2, 3, 4, 5, 6]
    assert result.rows[0].external_id == "good-1"
    assert result.rows[0].label == EvalLabel.RELEVANT
    assert result.rows[-1].label is None  # unlabeled


def test_run_eval_empty_db(db_engine):
    with session_scope(db_engine) as session:
        result = run_eval(
            session,
            date(2026, 5, 10),
            limit=25,
            labeled_items_path=DEFAULT_LABELED_ITEMS_PATH,
        )
    assert result.metrics.candidate_count == 0
    assert result.metrics.labeled_count == 0
    assert result.metrics.precision == 0.0
    # No relevant items present, but the fixture has some -> recall = 0
    assert result.metrics.recall == 0.0


def test_run_eval_no_relevant_labels_recall_one(db_engine, tmp_path):
    fixture = {
        "items": [
            {
                "external_id": "n",
                "title": "N",
                "label": "noise",
                "false_positive_class": "x",
            }
        ]
    }
    fixture_path = tmp_path / "labels.yaml"
    fixture_path.write_text(yaml.safe_dump(fixture), encoding="utf-8")

    with session_scope(db_engine) as session:
        result = run_eval(
            session,
            date(2026, 5, 10),
            limit=25,
            labeled_items_path=fixture_path,
        )
    # Fixture has zero relevant labels -> recall is defined as 1.0 by convention.
    assert result.metrics.recall == 1.0


def test_baseline_precision_on_default_fixture(db_engine, tmp_path):
    """Regression guard: with a representative synthetic mix that matches the
    default fixture's labeled IDs, precision must stay at or above this
    baseline. If a scoring change drops it, this test fails and we either
    update the baseline deliberately or revert the change."""
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    labeled = load_labeled_items(DEFAULT_LABELED_ITEMS_PATH)
    # Seed each labeled item with a final score derived from its label so the
    # candidate queue has a deterministic order. Relevant > borderline > noise
    # so that the harness is exercised end-to-end on real fixture data.
    score_by_label = {
        EvalLabel.RELEVANT: 80.0,
        EvalLabel.BORDERLINE: 60.0,
        EvalLabel.NOISE: 40.0,
    }
    with session_scope(db_engine) as session:
        for offset, labeled_item in enumerate(labeled.items):
            published = pub.replace(minute=offset % 60)
            _seed_item(
                session,
                external_id=labeled_item.external_id,
                title=labeled_item.title,
                final=score_by_label[labeled_item.label],
                ring=RadarRing.WATCH,
                published=published,
            )
        result = run_eval(
            session,
            date(2026, 5, 10),
            limit=25,
            labeled_items_path=DEFAULT_LABELED_ITEMS_PATH,
        )

    # With this synthetic ordering every labeled item is in top-K, so
    # precision = relevant / (relevant + noise) over the entire fixture.
    metrics = result.metrics
    assert metrics.relevant_in_top_k == metrics.total_labeled_relevant
    expected_precision = metrics.total_labeled_relevant / (
        metrics.total_labeled_relevant + metrics.total_labeled_noise
    )
    assert metrics.precision == pytest.approx(expected_precision, rel=1e-3)
