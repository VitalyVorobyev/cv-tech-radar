from __future__ import annotations

import json
from datetime import UTC, datetime

from radar.db import session_scope
from radar.filters.keyword_filter import classify_items_for_date
from radar.models import Item
from radar.reports.candidate_queue import collect_candidates, write_candidate_outputs


def test_candidate_queue_sorted_capped_and_written(db_engine, app_config, tmp_path):
    with session_scope(db_engine) as session:
        for index in range(30):
            session.add(
                Item(
                    type="paper",
                    title=f"Camera Calibration Bundle Adjustment {index:02d}",
                    normalized_title=f"camera calibration bundle adjustment {index:02d}",
                    abstract_or_summary=(
                        "Camera calibration, distortion, bundle adjustment, subpixel target "
                        "detection, multi-view reconstruction, point cloud metrology, and "
                        f"industrial inspection result {index}."
                    ),
                    url=f"https://example.test/{index}",
                    pdf_url=None,
                    published_at=datetime(2026, 5, 10, 10, index % 60, tzinfo=UTC),
                    updated_at=None,
                    source_name="arXiv cs.CV",
                    external_id=f"item-{index}",
                    arxiv_id=f"item-{index}",
                    authors_json=["Ada Vision"],
                    organizations_json=[],
                    metadata_json={},
                )
            )
        classify_items_for_date(session, app_config, datetime(2026, 5, 10).date())
        candidates = collect_candidates(
            session,
            datetime(2026, 5, 10).date(),
            limit=app_config.scoring.candidate_limit,
        )

    assert len(candidates) == 25
    scores = [candidate.scores.final for candidate in candidates]
    assert scores == sorted(scores, reverse=True)

    report_path, export_path = write_candidate_outputs(
        candidates,
        datetime(2026, 5, 10).date(),
        reports_dir=tmp_path / "reports",
        exports_dir=tmp_path / "exports",
    )
    report = report_path.read_text(encoding="utf-8")
    assert "# Candidate Queue - 2026-05-10" in report
    assert "### Claude decision" in report
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["date"] == "2026-05-10"
    assert len(payload["candidates"]) == 25
