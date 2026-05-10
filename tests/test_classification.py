from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from radar.filters.keyword_filter import classify_item, classify_items_for_date, keyword_matches
from radar.models import Item, Source


def make_item(title: str, summary: str) -> Item:
    return Item(
        type="paper",
        title=title,
        normalized_title=title.casefold(),
        abstract_or_summary=summary,
        url="https://example.test/item",
        pdf_url=None,
        published_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
        updated_at=None,
        source_name="arXiv cs.CV",
        external_id="x",
        arxiv_id="x",
        authors_json=[],
        organizations_json=[],
        metadata_json={},
    )


def test_classification_maps_calibration_geometry(app_config):
    item = make_item(
        "Camera Calibration for Multi-View 3D Reconstruction",
        "Bundle adjustment improves distortion and pose estimation for industrial cameras.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    result = classify_item(item, config=app_config, source=source)
    assert "Calibration & Camera Models" in result.tracks
    assert "3D Geometry & Reconstruction" in result.tracks
    assert result.final_score >= app_config.scoring.thresholds.watch


def test_negative_topics_reduce_score_without_hard_delete(app_config):
    clean = make_item(
        "Camera Calibration for Industrial Inspection",
        "Calibration, camera model, distortion, bundle adjustment, and machine vision metrology.",
    )
    noisy = make_item(
        "Camera Calibration for Industrial Inspection and Face Recognition",
        "Calibration, camera model, distortion, bundle adjustment, machine vision metrology, "
        "and face recognition.",
    )
    source = Source(key="arxiv-cs-cv", name="arXiv cs.CV", kind="arxiv", url="", priority=1)
    clean_result = classify_item(clean, config=app_config, source=source)
    noisy_result = classify_item(noisy, config=app_config, source=source)
    assert noisy_result.negative_topic_penalty > 0
    assert noisy_result.final_score < clean_result.final_score
    assert "Calibration & Camera Models" in noisy_result.tracks


def test_keyword_matching_avoids_substring_false_positives():
    assert keyword_matches("sam", "SAM improves segmentation.")
    assert keyword_matches("multi-view", "multi view reconstruction")
    assert not keyword_matches("sam", "temporal-window sampling strategy")
    assert not keyword_matches("tracking", "benchmarking detectors")


def test_classify_items_for_date_persists_results(db_engine, app_config):
    with db_engine.begin() as connection:
        connection.execute(
            Item.__table__.insert(),
            [
                {
                    "type": "paper",
                    "title": "Camera Calibration with Bundle Adjustment",
                    "normalized_title": "camera calibration with bundle adjustment",
                    "abstract_or_summary": "Subpixel calibration target detection.",
                    "url": "https://example.test/a",
                    "pdf_url": None,
                    "published_at": datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
                    "updated_at": None,
                    "source_name": "arXiv cs.CV",
                    "external_id": "a",
                    "doi": None,
                    "arxiv_id": "a",
                    "authors_json": [],
                    "organizations_json": [],
                    "metadata_json": {},
                }
            ],
        )
    with db_engine.begin() as connection:
        assert connection.execute(select(Item)).first() is not None
    from radar.db import session_scope
    from radar.models import ItemClassification

    with session_scope(db_engine) as session:
        count = classify_items_for_date(session, app_config, datetime(2026, 5, 10).date())
        assert count == 1
        stored = session.scalar(select(ItemClassification))
        assert stored is not None
        assert stored.recommended_ring != "Ignore"
