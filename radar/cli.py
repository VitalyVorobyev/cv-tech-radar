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
from sqlalchemy import select

from radar.collectors.arxiv import fetch_and_store_arxiv
from radar.config import ConfigError, load_app_config
from radar.curation import ProposalParseError, apply_proposals, parse_proposals_file
from radar.db import ensure_sources, get_engine, init_db, session_scope
from radar.decisions import DecisionError, list_decisions_for_date, parse_tracks, record_decision
from radar.embeddings import embed_items_for_date, find_near_duplicates
from radar.eval import DEFAULT_LABELED_ITEMS_PATH, render_eval_table, run_eval
from radar.filters.keyword_filter import classify_items_for_date
from radar.models import Item, Source
from radar.relevance_check import check_relevance_for_date
from radar.reports.candidate_queue import collect_candidates, write_candidate_outputs
from radar.reports.digest import collect_digest_rows, write_digest_outputs
from radar.reports.score_debug import collect_score_debug_rows
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


@app.command("apply")
def apply_command(
    markdown_path: Annotated[Path, typer.Argument(help="Candidate Markdown to apply.")],
    decided_by: Annotated[str, typer.Option("--decided-by")] = "claude-curator",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    db_path: Annotated[Path, typer.Option("--db-path")] = DefaultDbPath,
) -> None:
    """Bulk-record decisions written into a candidate Markdown file."""
    if not markdown_path.exists():
        raise typer.BadParameter(f"Markdown file not found: {markdown_path}")
    try:
        proposals = parse_proposals_file(markdown_path)
    except ProposalParseError as exc:
        raise typer.BadParameter(str(exc)) from exc

    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        try:
            report = apply_proposals(session, proposals, decided_by=decided_by, dry_run=dry_run)
        except ProposalParseError as exc:
            raise typer.BadParameter(str(exc)) from exc

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
        rows = collect_digest_rows(session, target_date, days)
        report_path, export_path = write_digest_outputs(
            session,
            rows,
            target_date,
            days,
            reports_dir=reports_dir,
            exports_dir=exports_dir,
        )
    console.print(f"Wrote digest ({len(rows)} item(s)): {report_path}")
    console.print(f"Wrote JSON export: {export_path}")


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
            summary = embed_items_for_date(
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
            summary = check_relevance_for_date(
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
