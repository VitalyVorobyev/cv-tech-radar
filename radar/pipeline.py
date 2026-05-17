"""Pipeline stage functions reusable from the CLI and the HTTP API.

Each `run_*` function takes a SQLAlchemy session, the relevant config slice,
and parameters, then returns a typed summary dataclass. Functions do not
print or raise typer-specific errors so they can be wrapped by both the CLI
(which translates to `typer.BadParameter`) and the FastAPI job runner
(which translates to `HTTPException`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import select

from radar.collectors.arxiv import ArxivFetchStats, fetch_and_store_arxiv
from radar.collectors.ecosystem.runner import EcosystemFetchStats, run_ecosystem_fetch
from radar.curation import (
    ApplyReport,
    ProposalParseError,
    apply_proposals,
    parse_proposals_file,
)
from radar.db import ensure_sources
from radar.embeddings import EmbedSummary, embed_items_for_date
from radar.filters.keyword_filter import classify_items_for_date
from radar.models import Item, Source
from radar.relevance_check import JudgmentSummary, check_relevance_for_date
from radar.reports.candidate_queue import collect_candidates, write_candidate_outputs
from radar.reports.digest import collect_digest_rows, write_digest_outputs
from radar.reports.ecosystem import collect_ecosystem_events
from radar.schemas import AppConfig, ChatSettings, EmbeddingsSettings


class ProgressCallback(Protocol):
    def __call__(self, index: int, total: int, item: Item, outcome: str) -> None: ...


@dataclass
class FetchArxivSummary:
    fetched: int = 0
    stored: int = 0
    updated: int = 0
    skipped_old: int = 0
    pages: int = 0
    latest_published_at: datetime | None = None
    rate_limited: bool = False
    http_errors: list[int] = field(default_factory=list)
    per_source: list[tuple[str, ArxivFetchStats]] = field(default_factory=list)


def run_fetch_arxiv(
    session,
    config: AppConfig,
    *,
    days: int,
    max_results: int,
    max_pages: int,
    page_delay_seconds: float = 3.0,
) -> FetchArxivSummary:
    summary = FetchArxivSummary()
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
            max_pages=max_pages,
            page_delay_seconds=page_delay_seconds,
        )
        summary.fetched += stats.fetched
        summary.stored += stats.stored
        summary.updated += stats.updated
        summary.skipped_old += stats.skipped_old
        summary.pages += stats.pages
        if stats.latest_published_at is not None and (
            summary.latest_published_at is None
            or stats.latest_published_at > summary.latest_published_at
        ):
            summary.latest_published_at = stats.latest_published_at
        if stats.rate_limited:
            summary.rate_limited = True
        if stats.http_errors:
            summary.http_errors.extend(stats.http_errors)
        summary.per_source.append((source_config.id, stats))
    return summary


def format_fetch_summary(summary: FetchArxivSummary) -> str:
    latest = (
        summary.latest_published_at.isoformat()
        if summary.latest_published_at is not None
        else "<none>"
    )
    msg = (
        f"arXiv: {summary.fetched} fetched ({summary.pages} page(s)) "
        f"— {summary.stored} new, {summary.updated} updated, "
        f"{summary.skipped_old} older than cutoff. Latest published: {latest}."
    )
    if summary.rate_limited:
        msg += (
            " [yellow]Rate-limited by arXiv (HTTP 429); stopped early. "
            "Retry in a few minutes.[/yellow]"
        )
    elif summary.http_errors:
        msg += f" [yellow]HTTP errors: {summary.http_errors}[/yellow]"
    return msg


@dataclass
class FetchEcosystemSummary:
    artifacts_synced: int = 0
    refs_polled: int = 0
    refs_ok: int = 0
    refs_not_found: int = 0
    refs_errored: int = 0
    events_created: int = 0
    per_ref_errors: list[tuple[str, str, str]] = field(default_factory=list)


def run_fetch_ecosystem(
    session,
    config: AppConfig,
    *,
    github_token: str | None = None,
) -> FetchEcosystemSummary:
    stats: EcosystemFetchStats = run_ecosystem_fetch(
        session,
        config,
        github_token=github_token,
    )
    return FetchEcosystemSummary(
        artifacts_synced=stats.artifacts_synced,
        refs_polled=stats.refs_polled,
        refs_ok=stats.refs_ok,
        refs_not_found=stats.refs_not_found,
        refs_errored=stats.refs_errored,
        events_created=stats.events_created,
        per_ref_errors=list(stats.per_ref_errors),
    )


def format_ecosystem_summary(summary: FetchEcosystemSummary) -> str:
    msg = (
        f"ecosystem: {summary.artifacts_synced} artifact(s) synced, "
        f"{summary.refs_polled} ref(s) polled "
        f"— {summary.refs_ok} ok, {summary.refs_not_found} not found, "
        f"{summary.refs_errored} errored. "
        f"{summary.events_created} new release event(s)."
    )
    if summary.per_ref_errors:
        msg += "\n[yellow]Ref failures:[/yellow]"
        for key, ecosystem, error in summary.per_ref_errors:
            msg += f"\n  [yellow]{key} ({ecosystem}): {error}[/yellow]"
    return msg


def run_classify(session, config: AppConfig, target_date) -> int:
    return classify_items_for_date(session, config, target_date)


@dataclass
class CandidatesSummary:
    count: int
    report_path: Path
    export_path: Path


def run_candidates(
    session,
    config: AppConfig,
    target_date,
    *,
    reports_dir: Path,
    exports_dir: Path,
) -> CandidatesSummary:
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
    return CandidatesSummary(
        count=len(candidates), report_path=report_path, export_path=export_path
    )


def run_apply(
    session,
    markdown_path: Path,
    *,
    decided_by: str,
    dry_run: bool,
) -> ApplyReport:
    """Parse decision YAML from `markdown_path` and write decisions.

    Raises `FileNotFoundError` if the path is missing, and re-raises
    `ProposalParseError` from the curation layer. Both CLI and API callers
    are expected to translate these into their native error types.
    """
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {markdown_path}")
    proposals = parse_proposals_file(markdown_path)
    return apply_proposals(session, proposals, decided_by=decided_by, dry_run=dry_run)


@dataclass
class DigestSummary:
    count: int
    report_path: Path
    export_path: Path


def run_digest(
    session,
    target_date,
    days: int,
    *,
    reports_dir: Path,
    exports_dir: Path,
) -> DigestSummary:
    rows = collect_digest_rows(session, target_date, days)
    ecosystem_events = collect_ecosystem_events(
        session,
        target_date=target_date,
        days=days,
        relevant_only=True,
    )
    report_path, export_path = write_digest_outputs(
        session,
        rows,
        target_date,
        days,
        reports_dir=reports_dir,
        exports_dir=exports_dir,
        ecosystem_events=ecosystem_events,
    )
    return DigestSummary(count=len(rows), report_path=report_path, export_path=export_path)


def run_embed(
    session,
    settings: EmbeddingsSettings,
    target_date,
    *,
    on_progress: ProgressCallback | None = None,
) -> EmbedSummary:
    return embed_items_for_date(
        session,
        settings,
        target_date,
        on_progress=on_progress,
    )


def run_relevance_check(
    session,
    chat_settings: ChatSettings,
    target_date,
    *,
    limit: int | None = None,
    on_progress: ProgressCallback | None = None,
    rejudge: bool = False,
) -> JudgmentSummary:
    return check_relevance_for_date(
        session,
        chat_settings,
        target_date,
        limit=limit,
        on_progress=on_progress,
        rejudge=rejudge,
    )


__all__ = [
    "ApplyReport",
    "CandidatesSummary",
    "DigestSummary",
    "EmbedSummary",
    "FetchArxivSummary",
    "FetchEcosystemSummary",
    "JudgmentSummary",
    "ProgressCallback",
    "ProposalParseError",
    "format_ecosystem_summary",
    "format_fetch_summary",
    "run_apply",
    "run_candidates",
    "run_classify",
    "run_digest",
    "run_embed",
    "run_fetch_arxiv",
    "run_fetch_ecosystem",
    "run_relevance_check",
]
