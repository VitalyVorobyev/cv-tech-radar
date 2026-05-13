"""Tests for `radar/pipeline.py`.

The CLI is tested separately in `test_cli.py`; this module exercises the
pure pipeline functions directly so they are usable from the API job
runner without going through Typer.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from radar.curation import ProposalParseError
from radar.db import session_scope
from radar.models import Item
from radar.pipeline import (
    CandidatesSummary,
    DigestSummary,
    FetchArxivSummary,
    format_fetch_summary,
    run_apply,
    run_candidates,
    run_classify,
    run_digest,
)


def _seed_item(engine, *, item_id: int, published: datetime) -> None:
    with session_scope(engine) as session:
        session.add(
            Item(
                id=item_id,
                type="paper",
                title=f"Camera Calibration with Bundle Adjustment {item_id}",
                normalized_title=f"camera calibration with bundle adjustment {item_id}",
                abstract_or_summary=(
                    "Subpixel calibration target detection for industrial cameras."
                ),
                url=f"https://example.test/{item_id}",
                pdf_url=None,
                published_at=published,
                updated_at=None,
                source_name="arXiv cs.CV",
                external_id=f"ext-{item_id}",
                arxiv_id=f"ext-{item_id}",
                authors_json=[],
                organizations_json=[],
                metadata_json={},
            )
        )


def test_run_classify_and_candidates_round_trip(db_engine, app_config, tmp_path):
    target_date = date(2026, 5, 10)
    _seed_item(db_engine, item_id=1, published=datetime(2026, 5, 10, 10, tzinfo=UTC))

    with session_scope(db_engine) as session:
        classified = run_classify(session, app_config, target_date)
    assert classified == 1

    reports_dir = tmp_path / "reports"
    exports_dir = tmp_path / "exports"
    with session_scope(db_engine) as session:
        summary = run_candidates(
            session,
            app_config,
            target_date,
            reports_dir=reports_dir,
            exports_dir=exports_dir,
        )
    assert isinstance(summary, CandidatesSummary)
    assert summary.count == 1
    assert summary.report_path == reports_dir / "2026-05-10.md"
    assert summary.report_path.exists()
    assert summary.export_path.exists()


def test_run_apply_raises_file_not_found(db_engine, tmp_path):
    missing = tmp_path / "nope.md"
    with session_scope(db_engine) as session, pytest.raises(FileNotFoundError):
        run_apply(session, missing, decided_by="tester", dry_run=False)


def test_run_apply_propagates_parse_error(db_engine, tmp_path):
    markdown = tmp_path / "bad.md"
    markdown.write_text(
        """## Candidate 1: Stub

- Item ID: 1

### Claude decision

```yaml
ring: NotAValidRing
```
""",
        encoding="utf-8",
    )
    with session_scope(db_engine) as session, pytest.raises(ProposalParseError):
        run_apply(session, markdown, decided_by="tester", dry_run=False)


def test_run_digest_writes_outputs(db_engine, tmp_path):
    target_date = date(2026, 5, 10)
    reports_dir = tmp_path / "reports/digests"
    exports_dir = tmp_path / "exports/digests"
    with session_scope(db_engine) as session:
        summary = run_digest(
            session,
            target_date,
            days=1,
            reports_dir=reports_dir,
            exports_dir=exports_dir,
        )
    assert isinstance(summary, DigestSummary)
    assert summary.report_path == reports_dir / "2026-05-10.md"
    assert summary.report_path.exists()
    assert summary.export_path.exists()


def test_format_fetch_summary_handles_rate_limit():
    summary = FetchArxivSummary(
        fetched=0,
        stored=0,
        updated=0,
        skipped_old=0,
        pages=0,
        latest_published_at=None,
        rate_limited=True,
    )
    msg = format_fetch_summary(summary)
    assert "Rate-limited" in msg
    assert "<none>" in msg


def test_format_fetch_summary_reports_http_errors():
    summary = FetchArxivSummary(
        fetched=10,
        stored=10,
        pages=1,
        latest_published_at=datetime(2026, 5, 11, tzinfo=UTC),
        http_errors=[500, 502],
    )
    msg = format_fetch_summary(summary)
    assert "HTTP errors" in msg
    assert "500" in msg


def test_pipeline_path_constants_are_paths():
    """Sanity check: summary dataclasses round-trip Path objects."""
    summary = CandidatesSummary(count=0, report_path=Path("a.md"), export_path=Path("a.json"))
    assert isinstance(summary.report_path, Path)
