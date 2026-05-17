from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from radar import cli as cli_module
from radar import pipeline as pipeline_module
from radar.cli import app
from radar.collectors.arxiv import ArxivFetchStats
from radar.db import get_engine, session_scope
from radar.models import Artifact, ArtifactDecision, Item, RadarDecision


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

    result = runner.invoke(
        app,
        ["score-debug", "--date", "2026-05-10", "--db-path", str(db_path)],
    )
    assert result.exit_code == 0
    assert "Score debug" in result.output

    result = runner.invoke(
        app,
        [
            "decide",
            "1",
            "--ring",
            "Watch",
            "--reason",
            "Relevant enough to track.",
            "--action",
            "Read PDF later.",
            "--decided-by",
            "tester",
            "--db-path",
            str(db_path),
        ],
    )
    assert result.exit_code == 0
    assert "Recorded decision" in result.output

    with session_scope(engine) as session:
        stored = session.query(RadarDecision).one()
        assert stored.ring == "Watch"

    result = runner.invoke(
        app,
        ["decisions", "--date", "2026-05-10", "--db-path", str(db_path)],
    )
    assert result.exit_code == 0
    assert "Relevant enough to track." in result.output


def _seed_items(engine, ids: list[int]) -> None:
    with session_scope(engine) as session:
        for item_id in ids:
            session.add(
                Item(
                    id=item_id,
                    type="paper",
                    title=f"Industrial calibration multi-camera bundle adjustment {item_id}",
                    normalized_title=(
                        f"industrial calibration multi-camera bundle adjustment {item_id}"
                    ),
                    abstract_or_summary=(
                        "Camera calibration with industrial bundle adjustment for "
                        "subpixel target detection."
                    ),
                    url=f"https://example.test/{item_id}",
                    pdf_url=None,
                    published_at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
                    updated_at=None,
                    source_name="arXiv cs.CV",
                    external_id=f"ext-{item_id}",
                    arxiv_id=f"ext-{item_id}",
                    authors_json=[],
                    organizations_json=[],
                    metadata_json={},
                )
            )


def test_daily_fetch_runs_fetch_classify_candidates(tmp_path, monkeypatch):
    runner = CliRunner()
    db_path = tmp_path / "radar.sqlite"
    reports_dir = tmp_path / "reports"
    exports_dir = tmp_path / "exports"

    # Init DB so seeding works, then stub the network-touching fetch step.
    result = runner.invoke(app, ["init-db", "--db-path", str(db_path)])
    assert result.exit_code == 0

    engine = get_engine(db_path)
    _seed_items(engine, [101, 102])

    fetch_called: list[dict] = []

    def fake_fetch(session, config, *, days, max_results, max_pages, page_delay_seconds=3.0):  # noqa: ARG001
        fetch_called.append({"days": days, "max_pages": max_pages})
        return pipeline_module.FetchArxivSummary(
            fetched=2,
            stored=2,
            updated=0,
            skipped_old=0,
            pages=1,
            latest_published_at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
            per_source=[("arxiv-cs-cv", ArxivFetchStats(fetched=2, stored=2, pages=1))],
        )

    monkeypatch.setattr(cli_module, "run_fetch_arxiv", fake_fetch)

    # Stub the ecosystem fetch too — daily-fetch now runs it, and we must not
    # touch the network in tests.
    ecosystem_called: list[bool] = []

    def fake_fetch_ecosystem(session, config, **_kwargs):  # noqa: ARG001
        ecosystem_called.append(True)
        return pipeline_module.FetchEcosystemSummary(artifacts_synced=3, refs_polled=5, refs_ok=5)

    monkeypatch.setattr(cli_module, "run_fetch_ecosystem", fake_fetch_ecosystem)

    result = runner.invoke(
        app,
        [
            "daily-fetch",
            "--date",
            "2026-05-11",
            "--days",
            "2",
            "--max-pages",
            "3",
            "--db-path",
            str(db_path),
            "--reports-dir",
            str(reports_dir),
            "--exports-dir",
            str(exports_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert fetch_called == [{"days": 2, "max_pages": 3}]
    assert ecosystem_called == [True]
    assert "arXiv:" in result.output
    assert "ecosystem:" in result.output
    assert "classify:" in result.output
    assert "candidates:" in result.output
    assert (reports_dir / "2026-05-11.md").exists()
    assert (exports_dir / "2026-05-11.json").exists()


def test_daily_publish_applies_and_writes_digest(tmp_path):
    runner = CliRunner()
    db_path = tmp_path / "radar.sqlite"
    digest_reports = tmp_path / "digests"
    digest_exports = tmp_path / "digest_exports"

    result = runner.invoke(app, ["init-db", "--db-path", str(db_path)])
    assert result.exit_code == 0

    engine = get_engine(db_path)
    _seed_items(engine, [101, 202, 303, 404])

    markdown = Path("tests/fixtures/candidates_filled.md")
    result = runner.invoke(
        app,
        [
            "daily-publish",
            str(markdown),
            "--date",
            "2026-05-11",
            "--days",
            "1",
            "--db-path",
            str(db_path),
            "--digest-reports-dir",
            str(digest_reports),
            "--digest-exports-dir",
            str(digest_exports),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Applied" in result.output
    assert "digest:" in result.output
    assert (digest_reports / "2026-05-11.md").exists()
    assert (digest_exports / "2026-05-11.json").exists()

    with session_scope(engine) as session:
        decisions = session.query(RadarDecision).all()
        assert {d.ring for d in decisions} >= {"Prototype", "Watch", "Ignore"}


def test_daily_publish_dry_run_skips_digest(tmp_path):
    runner = CliRunner()
    db_path = tmp_path / "radar.sqlite"
    digest_reports = tmp_path / "digests"

    result = runner.invoke(app, ["init-db", "--db-path", str(db_path)])
    assert result.exit_code == 0

    engine = get_engine(db_path)
    _seed_items(engine, [101, 202, 303, 404])

    result = runner.invoke(
        app,
        [
            "daily-publish",
            "tests/fixtures/candidates_filled.md",
            "--date",
            "2026-05-11",
            "--dry-run",
            "--db-path",
            str(db_path),
            "--digest-reports-dir",
            str(digest_reports),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Would apply" in result.output
    assert "digest:" not in result.output
    assert not digest_reports.exists()


def _seed_artifact(engine, key: str = "opencv") -> None:
    with session_scope(engine) as session:
        session.add(
            Artifact(
                key=key,
                name="OpenCV",
                status="adopted",
                capability="cv-imaging",
                tracks_json=["Open-Source CV Tooling"],
            )
        )


def test_artifact_decide_records_decision(tmp_path):
    runner = CliRunner()
    db_path = tmp_path / "radar.sqlite"
    assert runner.invoke(app, ["init-db", "--db-path", str(db_path)]).exit_code == 0
    engine = get_engine(db_path)
    _seed_artifact(engine)

    result = runner.invoke(
        app,
        [
            "artifact-decide",
            "opencv",
            "--ring",
            "Prototype",
            "--reason",
            "Worth a rig pass.",
            "--db-path",
            str(db_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Recorded artifact decision" in result.output

    with session_scope(engine) as session:
        stored = session.query(ArtifactDecision).one()
        assert stored.ring == "Prototype"
        # --tracks omitted → defaults to the artifact's own tracks.
        assert stored.tracks_json == ["Open-Source CV Tooling"]


def test_artifact_decide_unknown_key_errors(tmp_path):
    runner = CliRunner()
    db_path = tmp_path / "radar.sqlite"
    runner.invoke(app, ["init-db", "--db-path", str(db_path)])
    result = runner.invoke(
        app,
        [
            "artifact-decide",
            "does-not-exist",
            "--ring",
            "Watch",
            "--reason",
            "x",
            "--db-path",
            str(db_path),
        ],
    )
    assert result.exit_code != 0
