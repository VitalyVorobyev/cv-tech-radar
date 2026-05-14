from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from radar.config import ConfigError, load_app_config
from radar.curation import ProposalParseError
from radar.db import ensure_sources, get_engine, init_db, session_scope
from radar.decisions import DecisionError, list_decisions_for_date, parse_tracks, record_decision
from radar.embeddings import find_near_duplicates
from radar.eval import DEFAULT_LABELED_ITEMS_PATH, render_eval_table, run_eval
from radar.models import Item
from radar.pipeline import (
    format_fetch_summary,
    run_apply,
    run_candidates,
    run_classify,
    run_digest,
    run_embed,
    run_fetch_arxiv,
    run_relevance_check,
)
from radar.reports.score_debug import collect_score_debug_rows
from radar.reports.static_bundle import BUNDLE_FILES, build_static_bundle
from radar.schemas import RadarRing
from radar.utils import parse_date_arg

app = typer.Typer(help="CV Radar command line interface.")
console = Console()
DefaultDbPath = Path("data/radar.sqlite")
DefaultConfigDir = Path("config")
DefaultReportsDir = Path("reports/candidates")
DefaultExportsDir = Path("data/exports/candidates")
DefaultDigestReportsDir = Path("reports/digests")
DefaultDigestExportsDir = Path("data/exports/digests")


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
    max_pages: Annotated[
        int,
        typer.Option(
            "--max-pages",
            min=1,
            help="Walk up to N pages of --max-results each, stopping early "
            "once entries cross the --days cutoff.",
        ),
    ] = 10,
    page_delay_seconds: Annotated[
        float,
        typer.Option(
            "--page-delay",
            min=0.0,
            help="Seconds to wait between successive page fetches. "
            "Default 3.0 honors arXiv's API etiquette and avoids HTTP 429.",
        ),
    ] = 3.0,
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
    config_dir: Annotated[Path, typer.Option("--config-dir")] = DefaultConfigDir,
) -> None:
    """Fetch recent papers from enabled arXiv sources."""
    config = _load(config_dir)
    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        summary = run_fetch_arxiv(
            session,
            config,
            days=days,
            max_results=max_results,
            max_pages=max_pages,
            page_delay_seconds=page_delay_seconds,
        )
    console.print(format_fetch_summary(summary))


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
        count = run_classify(session, config, target_date)
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
        summary = run_candidates(
            session,
            config,
            target_date,
            reports_dir=reports_dir,
            exports_dir=exports_dir,
        )
    console.print(f"Wrote {summary.count} candidate(s): {summary.report_path}")
    console.print(f"Wrote JSON export: {summary.export_path}")


@app.command("decide")
def decide_command(
    item_id: Annotated[int, typer.Argument(help="SQLite item id to decide.")],
    ring: Annotated[RadarRing, typer.Option("--ring", case_sensitive=False)],
    reason: Annotated[str, typer.Option("--reason", help="Short decision rationale.")],
    action: Annotated[str, typer.Option("--action", help="Next action or disposition.")] = "",
    tracks: Annotated[
        str | None,
        typer.Option(
            "--tracks",
            help="Comma-separated track names. Defaults to classifier tracks.",
        ),
    ] = None,
    decided_by: Annotated[str, typer.Option("--decided-by")] = "codex",
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
) -> None:
    """Record a durable radar decision for an item."""
    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        try:
            decision = record_decision(
                session,
                item_id=item_id,
                ring=ring,
                tracks=parse_tracks(tracks),
                reason=reason,
                action=action,
                decided_by=decided_by,
            )
        except DecisionError as exc:
            raise typer.BadParameter(str(exc)) from exc
        console.print(f"Recorded decision {decision.id}: item {item_id} -> {decision.ring}")


def _cli_run_apply(session, markdown_path: Path, *, decided_by: str, dry_run: bool):
    try:
        return run_apply(session, markdown_path, decided_by=decided_by, dry_run=dry_run)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except ProposalParseError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _print_apply_report(report, *, dry_run: bool) -> None:
    label = "Would apply" if dry_run else "Applied"
    console.print(
        f"{label} {len(report.applied)} decision(s); "
        f"skipped {len(report.skipped)}; warnings {len(report.warnings)}"
    )
    for parsed in report.applied:
        proposal = parsed.proposal
        if proposal is None:
            continue
        ring = proposal.ring.value if hasattr(proposal.ring, "value") else str(proposal.ring)
        console.print(f"  item {parsed.item_id} -> {ring}: {proposal.reason[:80]}")
    for parsed in report.skipped:
        console.print(f"  skipped item {parsed.item_id}: {parsed.skipped_reason}")
    for warning in report.warnings:
        console.print(f"  warning: {warning}")


@app.command("apply")
def apply_command(
    markdown_path: Annotated[Path, typer.Argument(help="Candidate Markdown to apply.")],
    decided_by: Annotated[str, typer.Option("--decided-by")] = "claude-curator",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
) -> None:
    """Bulk-record decisions written into a candidate Markdown file."""
    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        report = _cli_run_apply(session, markdown_path, decided_by=decided_by, dry_run=dry_run)
    _print_apply_report(report, dry_run=dry_run)


@app.command("digest")
def digest_command(
    date: Annotated[str, typer.Option("--date")] = "today",
    days: Annotated[int, typer.Option("--days", min=1)] = 1,
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
    reports_dir: Annotated[Path, typer.Option("--reports-dir")] = DefaultDigestReportsDir,
    exports_dir: Annotated[Path, typer.Option("--exports-dir")] = DefaultDigestExportsDir,
) -> None:
    """Generate a short daily digest Markdown from recorded decisions."""
    target_date = parse_date_arg(date)
    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        summary = run_digest(
            session,
            target_date,
            days,
            reports_dir=reports_dir,
            exports_dir=exports_dir,
        )
    console.print(f"Wrote digest ({summary.count} item(s)): {summary.report_path}")
    console.print(f"Wrote JSON export: {summary.export_path}")


DefaultStaticTargetDir = Path("frontend/public/data")


@app.command("build-static")
def build_static_command(
    target: Annotated[Path, typer.Option("--target")] = DefaultStaticTargetDir,
    weeks: Annotated[int, typer.Option("--weeks", min=1, max=52)] = 26,
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
    config_dir: Annotated[Path, typer.Option("--config-dir")] = DefaultConfigDir,
) -> None:
    """Pre-render the public radar state into static JSON files.

    Writes board.json / tracks.json / timeline.json / meta.json plus per-item
    JSON under ``items/`` so a no-backend Vite build can serve the radar.
    """
    config = _load(config_dir)
    engine = get_engine(db_path)
    with session_scope(engine) as session:
        paths = build_static_bundle(target, session=session, config=config, weeks=weeks)
    for name in BUNDLE_FILES:
        key = name.removesuffix(".json")
        console.print(f"Wrote {paths[key]}")
    console.print(f"Wrote per-item JSON under {target / 'items'}/")


@app.command("daily-fetch")
def daily_fetch_command(
    days: Annotated[int, typer.Option("--days", min=1)] = 1,
    max_results: Annotated[int, typer.Option("--max-results", min=1)] = 100,
    max_pages: Annotated[int, typer.Option("--max-pages", min=1)] = 10,
    page_delay_seconds: Annotated[float, typer.Option("--page-delay", min=0.0)] = 3.0,
    date: Annotated[str, typer.Option("--date")] = "today",
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
    config_dir: Annotated[Path, typer.Option("--config-dir")] = DefaultConfigDir,
    reports_dir: Annotated[Path, typer.Option("--reports-dir")] = DefaultReportsDir,
    exports_dir: Annotated[Path, typer.Option("--exports-dir")] = DefaultExportsDir,
) -> None:
    """Run fetch → classify → candidates in a single transaction.

    Stops before curation: the printed candidate Markdown path is where the
    human picks up.
    """
    config = _load(config_dir)
    target_date = parse_date_arg(date)
    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        fetch_summary = run_fetch_arxiv(
            session,
            config,
            days=days,
            max_results=max_results,
            max_pages=max_pages,
            page_delay_seconds=page_delay_seconds,
        )
        classified = run_classify(session, config, target_date)
        candidates_summary = run_candidates(
            session,
            config,
            target_date,
            reports_dir=reports_dir,
            exports_dir=exports_dir,
        )
    console.print(format_fetch_summary(fetch_summary))
    console.print(f"classify: {classified} item(s) for {target_date.isoformat()}")
    console.print(
        f"candidates: {candidates_summary.count} written to {candidates_summary.report_path}"
    )
    console.print(f"next: curate {candidates_summary.report_path}, then `radar daily-publish`.")


@app.command("daily-publish")
def daily_publish_command(
    markdown_path: Annotated[
        Path, typer.Argument(help="Candidate Markdown with filled decisions.")
    ],
    date: Annotated[str, typer.Option("--date")] = "today",
    days: Annotated[int, typer.Option("--days", min=1)] = 1,
    decided_by: Annotated[str, typer.Option("--decided-by")] = "claude-curator",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
    config_dir: Annotated[Path, typer.Option("--config-dir")] = DefaultConfigDir,
    digest_reports_dir: Annotated[
        Path, typer.Option("--digest-reports-dir")
    ] = DefaultDigestReportsDir,
    digest_exports_dir: Annotated[
        Path, typer.Option("--digest-exports-dir")
    ] = DefaultDigestExportsDir,
) -> None:
    """Apply curator decisions from a candidate Markdown and write the digest."""
    _load(config_dir)
    target_date = parse_date_arg(date)
    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        report = _cli_run_apply(session, markdown_path, decided_by=decided_by, dry_run=dry_run)
        if dry_run:
            digest_summary = None
        else:
            digest_summary = run_digest(
                session,
                target_date,
                days,
                reports_dir=digest_reports_dir,
                exports_dir=digest_exports_dir,
            )
    _print_apply_report(report, dry_run=dry_run)
    if digest_summary is not None:
        console.print(f"digest: {digest_summary.count} item(s) -> {digest_summary.report_path}")
        console.print(f"digest JSON: {digest_summary.export_path}")


@app.command("decisions")
def decisions_command(
    date: Annotated[str, typer.Option("--date")] = "today",
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
) -> None:
    """List radar decisions for items published on a date."""
    target_date = parse_date_arg(date)
    engine = get_engine(db_path)
    init_db(engine)
    table = Table(title=f"Radar decisions - {target_date.isoformat()}")
    table.add_column("Item")
    table.add_column("Ring")
    table.add_column("Tracks")
    table.add_column("Reason", overflow="fold")
    table.add_column("Action", overflow="fold")
    detail_lines: list[str] = []
    with session_scope(engine) as session:
        rows = list_decisions_for_date(session, target_date)
        for item, decision in rows:
            detail_lines.append(
                f"{item.id} {decision.ring}: {decision.decision_reason} | {decision.action}"
            )
            table.add_row(
                str(item.id),
                decision.ring,
                ", ".join(decision.tracks_json or []),
                decision.decision_reason,
                decision.action,
            )
    console.print(table)
    for line in detail_lines:
        console.print(line)
    console.print(f"{len(rows)} decision(s)")


@app.command("serve")
def serve_command(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 7878,
    reload: Annotated[bool, typer.Option("--reload")] = False,
    open_browser: Annotated[bool, typer.Option("--open", "-o")] = False,
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
    config_dir: Annotated[Path, typer.Option("--config-dir")] = DefaultConfigDir,
) -> None:
    """Run the FastAPI HTTP server for the curation UI."""
    import uvicorn

    from radar.api.app import create_app

    # Validate config early so misconfigurations fail fast.
    _load(config_dir)

    if open_browser:
        url = f"http://{host}:{port}"

        def _open() -> None:
            webbrowser.open(url)

        threading.Timer(1.0, _open).start()

    if reload:
        # uvicorn's reload mode requires an import string, not an app instance.
        # Pass settings via env vars so the reloaded process can pick them up.
        import os

        os.environ["CV_RADAR_DB_PATH"] = str(db_path)
        os.environ["CV_RADAR_CONFIG_DIR"] = str(config_dir)
        uvicorn.run(
            "radar.api.app:_app_for_reload",
            host=host,
            port=port,
            reload=True,
            factory=True,
        )
        return

    app_instance = create_app(db_path=db_path, config_dir=config_dir)
    uvicorn.run(app_instance, host=host, port=port)


def _ollama_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )


def _short_title(item: Item, *, width: int = 60) -> str:
    title = item.title or ""
    if len(title) <= width:
        return title
    return title[: width - 1].rstrip() + "…"


@app.command("embed")
def embed_command(
    date: Annotated[str, typer.Option("--date")] = "today",
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
    config_dir: Annotated[Path, typer.Option("--config-dir")] = DefaultConfigDir,
) -> None:
    """Compute Ollama embeddings for items published on a date."""
    config = _load(config_dir)
    target_date = parse_date_arg(date)
    engine = get_engine(db_path)
    init_db(engine)
    with _ollama_progress() as progress:
        task_id = progress.add_task("Embedding items", total=None)
        total_set = False

        def on_progress(index: int, total: int, item: Item, outcome: str) -> None:
            nonlocal total_set
            if not total_set:
                progress.update(task_id, total=total)
                total_set = True
            progress.update(
                task_id,
                advance=1,
                description=f"[{outcome}] {_short_title(item)}",
            )

        with session_scope(engine) as session:
            summary = run_embed(
                session,
                config.embeddings.embeddings,
                target_date,
                on_progress=on_progress,
            )
    console.print(
        f"Embedded {summary.embedded} new item(s); skipped {summary.skipped} already-embedded; "
        f"total in window: {summary.total}"
    )


@app.command("near-duplicates")
def near_duplicates_command(
    date: Annotated[str, typer.Option("--date")] = "today",
    days: Annotated[int, typer.Option("--days", min=1)] = 14,
    threshold: Annotated[
        float | None,
        typer.Option("--threshold", min=0.0, max=1.0, help="Override config threshold."),
    ] = None,
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
    config_dir: Annotated[Path, typer.Option("--config-dir")] = DefaultConfigDir,
) -> None:
    """Report near-duplicate items based on stored embeddings."""
    config = _load(config_dir)
    target_date = parse_date_arg(date)
    settings = config.embeddings.embeddings
    cutoff = threshold if threshold is not None else settings.near_duplicate_threshold
    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        pairs = find_near_duplicates(
            session,
            target_date,
            days=days,
            threshold=cutoff,
            model=settings.model,
        )
    if not pairs:
        console.print(f"No near-duplicates above cosine {cutoff:.3f} in the last {days} day(s).")
        return
    table = Table(title=f"Near-duplicates >= {cutoff:.3f} (last {days} day(s))")
    table.add_column("Cosine", justify="right")
    table.add_column("A id")
    table.add_column("A ext")
    table.add_column("A title", overflow="fold")
    table.add_column("B id")
    table.add_column("B ext")
    table.add_column("B title", overflow="fold")
    for pair in pairs:
        table.add_row(
            f"{pair.cosine:.4f}",
            str(pair.item_a_id),
            pair.item_a_external_id or "",
            pair.item_a_title,
            str(pair.item_b_id),
            pair.item_b_external_id or "",
            pair.item_b_title,
        )
    console.print(table)
    console.print(f"{len(pairs)} pair(s) above threshold.")


@app.command("relevance-check")
def relevance_check_command(
    date: Annotated[str, typer.Option("--date")] = "today",
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Cap how many classified items to judge."),
    ] = None,
    rejudge: Annotated[
        bool,
        typer.Option(
            "--rejudge",
            help="Replace existing judgments for the configured model instead of skipping.",
        ),
    ] = False,
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
    config_dir: Annotated[Path, typer.Option("--config-dir")] = DefaultConfigDir,
) -> None:
    """Ask the local chat model for yes/no relevance on each classified candidate.

    Shadow only: results are written to `item_llm_judgments` and never affect
    the candidate queue. Re-runs with the same model skip already-judged items
    unless `--rejudge` is passed.
    """
    config = _load(config_dir)
    target_date = parse_date_arg(date)
    engine = get_engine(db_path)
    init_db(engine)
    with _ollama_progress() as progress:
        task_id = progress.add_task("Judging candidates", total=None)
        total_set = False

        def on_progress(index: int, total: int, item: Item, outcome: str) -> None:
            nonlocal total_set
            if not total_set:
                progress.update(task_id, total=total)
                total_set = True
            progress.update(
                task_id,
                advance=1,
                description=f"[{outcome}] {_short_title(item)}",
            )

        with session_scope(engine) as session:
            summary = run_relevance_check(
                session,
                config.embeddings.chat,
                target_date,
                limit=limit,
                on_progress=on_progress,
                rejudge=rejudge,
            )
    console.print(
        f"Judged {summary.judged} of {summary.total} item(s); "
        f"skipped {summary.skipped} already-judged; failed {summary.failed}"
    )
    console.print(
        f"Decisions: yes={summary.yes_count}, no={summary.no_count}, "
        f"unknown={summary.unknown_count}"
    )
    if summary.failed > 0:
        console.print(
            f"[yellow]{summary.failed} item(s) failed.[/yellow] If using a "
            "reasoning model (e.g. gemma4:e2b), check that chat.max_tokens "
            "is large enough — the model may be burning the budget on internal "
            "reasoning before producing visible output. Try `--rejudge` after "
            "raising the value in config/embeddings.yaml."
        )
    if summary.unknown_count > 0 and summary.judged == summary.unknown_count:
        console.print(
            "[yellow]All judged items came back as 'unknown'.[/yellow] The "
            "model may not be following the DECISION/REASON format. Inspect "
            "raw_response in the item_llm_judgments table and adjust the "
            "prompt or switch models."
        )


@app.command("eval")
def eval_command(
    date: Annotated[str, typer.Option("--date")] = "today",
    limit: Annotated[int, typer.Option("--limit", min=1)] = 25,
    fixture: Annotated[Path, typer.Option("--fixture")] = DEFAULT_LABELED_ITEMS_PATH,
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
    config_dir: Annotated[Path, typer.Option("--config-dir")] = DefaultConfigDir,
) -> None:
    """Score the candidate queue for a date against a labeled set."""
    _load(config_dir)
    target_date = parse_date_arg(date)
    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        result = run_eval(
            session,
            target_date,
            limit=limit,
            labeled_items_path=fixture,
        )

    console.print(render_eval_table(result))
    metrics = result.metrics
    console.print()
    console.print(
        f"top-{result.limit}: {metrics.candidate_count} candidates, "
        f"{metrics.labeled_count} labeled "
        f"(relevant={metrics.relevant_in_top_k}, "
        f"borderline={metrics.borderline_in_top_k}, "
        f"noise={metrics.noise_in_top_k}, "
        f"unlabeled={metrics.unlabeled_in_top_k})"
    )
    console.print(
        f"precision: {metrics.precision:.3f}  recall: {metrics.recall:.3f}  "
        f"(fixture totals: relevant={metrics.total_labeled_relevant}, "
        f"noise={metrics.total_labeled_noise})"
    )
    if metrics.false_positive_classes:
        console.print("false-positive classes in top-K:")
        for cls, count in sorted(metrics.false_positive_classes.items()):
            console.print(f"  {cls}: {count}")
    if metrics.missing_relevant_external_ids:
        console.print(
            "labeled-relevant items missing from top-K: "
            + ", ".join(metrics.missing_relevant_external_ids)
        )


@app.command("score-debug")
def score_debug_command(
    date: Annotated[str, typer.Option("--date")] = "today",
    limit: Annotated[int, typer.Option("--limit", min=1)] = 25,
    include_zero: Annotated[bool, typer.Option("--include-zero")] = False,
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
) -> None:
    """Show score components and matched keywords for classified items."""
    target_date = parse_date_arg(date)
    engine = get_engine(db_path)
    init_db(engine)
    table = Table(title=f"Score debug - {target_date.isoformat()}")
    table.add_column("Item")
    table.add_column("Final", justify="right")
    table.add_column("Ring")
    table.add_column("Rel", justify="right")
    table.add_column("Src", justify="right")
    table.add_column("Impl", justify="right")
    table.add_column("Novel", justify="right")
    table.add_column("Neg", justify="right")
    table.add_column("Tracks")
    table.add_column("Keywords")
    table.add_column("Title")
    detail_lines: list[str] = []
    with session_scope(engine) as session:
        rows = collect_score_debug_rows(
            session,
            target_date,
            limit=limit,
            include_zero=include_zero,
        )
        for item, classification in rows:
            detail_lines.append(
                f"{item.id} final={classification.final_score:g} "
                f"ring={classification.recommended_ring} "
                f"tracks={', '.join(classification.tracks_json or [])} "
                f"keywords={', '.join(classification.positive_keywords_json or [])} "
                f"title={item.title}"
            )
            table.add_row(
                str(item.id),
                f"{classification.final_score:g}",
                classification.recommended_ring,
                f"{classification.relevance_score:g}",
                f"{classification.source_priority_score:g}",
                f"{classification.implementation_score:g}",
                f"{classification.novelty_score:g}",
                f"{classification.negative_topic_penalty:g}",
                ", ".join(classification.tracks_json or []),
                ", ".join(classification.positive_keywords_json or []),
                item.title,
            )
    console.print(table)
    for line in detail_lines:
        console.print(line)
    console.print(f"{len(rows)} row(s)")
