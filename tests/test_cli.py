from __future__ import annotations

from datetime import UTC, datetime

from typer.testing import CliRunner

from radar.cli import app
from radar.db import get_engine, session_scope
from radar.models import Item


def test_cli_smoke_init_classify_candidates(tmp_path):
    runner = CliRunner()
    db_path = tmp_path / "radar.sqlite"
    reports_dir = tmp_path / "reports"
    exports_dir = tmp_path / "exports"

    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "CV Radar" in result.output

    result = runner.invoke(app, ["init-db", "--db-path", str(db_path)])
    assert result.exit_code == 0

    engine = get_engine(db_path)
    with session_scope(engine) as session:
        session.add(
            Item(
                type="paper",
                title="Camera Calibration with Bundle Adjustment",
                normalized_title="camera calibration with bundle adjustment",
                abstract_or_summary="Subpixel calibration target detection for industrial cameras.",
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
            )
        )

    result = runner.invoke(
        app,
        ["classify", "--date", "2026-05-10", "--db-path", str(db_path)],
    )
    assert result.exit_code == 0

    result = runner.invoke(
        app,
        [
            "candidates",
            "--date",
            "2026-05-10",
            "--db-path",
            str(db_path),
            "--reports-dir",
            str(reports_dir),
            "--exports-dir",
            str(exports_dir),
        ],
    )
    assert result.exit_code == 0
    assert (reports_dir / "2026-05-10.md").exists()
    assert (exports_dir / "2026-05-10.json").exists()
