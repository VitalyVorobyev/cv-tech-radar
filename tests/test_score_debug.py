from __future__ import annotations

from datetime import UTC, datetime

from radar.db import session_scope
from radar.filters.keyword_filter import classify_items_for_date
from radar.models import Item
from radar.reports.score_debug import collect_score_debug_rows


def test_collect_score_debug_rows_orders_by_score(db_engine, app_config):
    with session_scope(db_engine) as session:
        session.add_all(
            [
                Item(
                    type="paper",
                    title="Camera Calibration with Bundle Adjustment",
                    normalized_title="camera calibration with bundle adjustment",
                    abstract_or_summary="Subpixel calibration target detection.",
                    url="https://example.test/a",
                    pdf_url=None,
                    published_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
                    updated_at=None,
                    source_name="arXiv cs.CV",
                    external_id="a",
                    arxiv_id="a",
                    authors_json=[],
                    organizations_json=[],
                    metadata_json={},
                ),
                Item(
                    type="paper",
                    title="Unrelated Painting Style Transfer",
                    normalized_title="unrelated painting style transfer",
                    abstract_or_summary="No configured radar signal.",
                    url="https://example.test/b",
                    pdf_url=None,
                    published_at=datetime(2026, 5, 10, 11, 0, tzinfo=UTC),
                    updated_at=None,
                    source_name="arXiv cs.CV",
                    external_id="b",
                    arxiv_id="b",
                    authors_json=[],
                    organizations_json=[],
                    metadata_json={},
                ),
            ]
        )
        classify_items_for_date(session, app_config, datetime(2026, 5, 10).date())
        rows = collect_score_debug_rows(session, datetime(2026, 5, 10).date(), limit=10)
        assert len(rows) == 1
        assert rows[0][0].title == "Camera Calibration with Bundle Adjustment"
        assert rows[0][1].final_score > 0
