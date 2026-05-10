from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from sqlalchemy import select

from radar.collectors.arxiv import fetch_and_store_arxiv
from radar.config import ConfigError, load_app_config
from radar.db import ensure_sources, get_engine, init_db, session_scope
from radar.filters.keyword_filter import classify_items_for_date
from radar.models import Source
from radar.reports.candidate_queue import collect_candidates, write_candidate_outputs
from radar.utils import parse_date_arg

app = typer.Typer(help="CV Radar command line interface.")
console = Console()
DefaultDbPath = Path("data/radar.sqlite")
DefaultConfigDir = Path("config")
DefaultReportsDir = Path("reports/candidates")
DefaultExportsDir = Path("data/exports/candidates")


def _load(config_dir: Path):
    try:
        return load_app_config(config_dir)
    except ConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("init-db")
def init_db_command(
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
    config_dir: Annotated[Path, typer.Option("--config-dir")] = DefaultConfigDir,
) -> None:
    """Create SQLite tables and synchronize configured sources."""
    config = _load(config_dir)
    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        ensure_sources(session, config.sources)
    console.print(f"Initialized database: {db_path}")


@app.command("fetch-arxiv")
def fetch_arxiv_command(
    days: Annotated[int, typer.Option("--days", min=1)] = 1,
    max_results: Annotated[int, typer.Option("--max-results", min=1)] = 100,
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
    config_dir: Annotated[Path, typer.Option("--config-dir")] = DefaultConfigDir,
) -> None:
    """Fetch recent papers from enabled arXiv sources."""
    config = _load(config_dir)
    engine = get_engine(db_path)
    init_db(engine)
    total_fetched = total_stored = total_updated = total_skipped = 0
    with session_scope(engine) as session:
        ensure_sources(session, config.sources)
        for source_config in config.sources.sources:
            if not source_config.enabled or source_config.kind != "arxiv":
                continue
            source = session.scalar(select(Source).where(Source.key == source_config.id))
            if source is None:
                continue
            stats = fetch_and_store_arxiv(
                session,
                source,
                source_config,
                days=days,
                max_results=max_results,
            )
            total_fetched += stats.fetched
            total_stored += stats.stored
            total_updated += stats.updated
            total_skipped += stats.skipped_old
    console.print(
        "Fetched arXiv entries: "
        f"{total_fetched}; stored: {total_stored}; updated: {total_updated}; "
        f"skipped old: {total_skipped}"
    )


@app.command("classify")
def classify_command(
    date: Annotated[str, typer.Option("--date")] = "today",
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
    config_dir: Annotated[Path, typer.Option("--config-dir")] = DefaultConfigDir,
) -> None:
    """Classify stored items for a date."""
    config = _load(config_dir)
    target_date = parse_date_arg(date)
    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        count = classify_items_for_date(session, config, target_date)
    console.print(f"Classified {count} item(s) for {target_date.isoformat()}")


@app.command("candidates")
def candidates_command(
    date: Annotated[str, typer.Option("--date")] = "today",
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
    config_dir: Annotated[Path, typer.Option("--config-dir")] = DefaultConfigDir,
    reports_dir: Annotated[Path, typer.Option("--reports-dir")] = DefaultReportsDir,
    exports_dir: Annotated[Path, typer.Option("--exports-dir")] = DefaultExportsDir,
) -> None:
    """Generate the candidate queue Markdown and JSON debug export."""
    config = _load(config_dir)
    target_date = parse_date_arg(date)
    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        candidates = collect_candidates(
            session,
            target_date,
            limit=config.scoring.candidate_limit,
        )
    report_path, export_path = write_candidate_outputs(
        candidates,
        target_date,
        reports_dir=reports_dir,
        exports_dir=exports_dir,
    )
    console.print(f"Wrote {len(candidates)} candidate(s): {report_path}")
    console.print(f"Wrote JSON export: {export_path}")
