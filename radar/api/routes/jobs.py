"""REST endpoints for asynchronous pipeline jobs.

Each ``POST`` returns ``202 Accepted`` immediately with a job id. The
actual work happens in a worker thread that opens its own SQLAlchemy
session — sessions are not safe to pass across thread boundaries.

Stage payloads mirror the ``run_*`` functions in :mod:`radar.pipeline`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query, status
from pydantic import BaseModel, Field

from radar.api.deps import get_settings
from radar.config import load_app_config
from radar.curation import ProposalParseError
from radar.db import get_engine, init_db, session_scope
from radar.jobs import Job, get_registry
from radar.pipeline import (
    run_apply,
    run_candidates,
    run_classify,
    run_digest,
    run_embed,
    run_fetch_arxiv,
    run_relevance_check,
)
from radar.utils import parse_date_arg

router = APIRouter(prefix="/jobs", tags=["jobs"])

DefaultReportsDir = Path("reports/candidates")
DefaultExportsDir = Path("data/exports/candidates")
DefaultDigestReportsDir = Path("reports/digests")
DefaultDigestExportsDir = Path("data/exports/digests")


def _resolve_config():
    """Load the current app config inside the worker thread.

    The main thread's cached config is reused when possible. We tolerate
    a fresh load if the cache was cleared between submission and
    execution.
    """
    settings = get_settings()
    config_dir = settings.config_dir or Path("config")
    return load_app_config(config_dir)


def _build_engine():
    settings = get_settings()
    engine = get_engine(settings.db_path)
    init_db(engine)
    return engine


def _parse_date(value: str):
    try:
        return parse_date_arg(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid date: {exc}") from exc


def _accepted(job: Job) -> dict:
    return {"job_id": job.id, "stage": job.stage, "state": job.state}


class FetchPayload(BaseModel):
    days: int = Field(default=1, ge=1)
    max_results: int = Field(default=100, ge=1)
    max_pages: int = Field(default=10, ge=1)
    page_delay_seconds: float = Field(default=3.0, ge=0.0)


class DatePayload(BaseModel):
    date: str = "today"


class DigestPayload(BaseModel):
    date: str = "today"
    days: int = Field(default=1, ge=1)


class ApplyPayload(BaseModel):
    markdown_path: str = Field(min_length=1)
    decided_by: str = "ui-curator"
    dry_run: bool = False


class RelevancePayload(BaseModel):
    date: str = "today"
    limit: int | None = Field(default=None, ge=1)
    rejudge: bool = False


class DailyIterationPayload(BaseModel):
    fetch: FetchPayload = Field(default_factory=FetchPayload)
    date: str = "today"


@router.post(
    "/fetch",
    status_code=status.HTTP_202_ACCEPTED,
)
def post_fetch_job(payload: Annotated[FetchPayload | None, Body()] = None) -> dict:
    payload = payload or FetchPayload()

    def _run(job: Job) -> dict:
        config = _resolve_config()
        engine = _build_engine()
        job.log.append("fetch: starting arXiv fetch")
        with session_scope(engine) as session:
            summary = run_fetch_arxiv(
                session,
                config,
                days=payload.days,
                max_results=payload.max_results,
                max_pages=payload.max_pages,
                page_delay_seconds=payload.page_delay_seconds,
            )
        latest = (
            summary.latest_published_at.isoformat()
            if summary.latest_published_at is not None
            else None
        )
        job.log.append(
            f"fetch: stored {summary.stored} new, updated {summary.updated}, "
            f"skipped_old {summary.skipped_old}"
        )
        return {
            "fetched": summary.fetched,
            "stored": summary.stored,
            "updated": summary.updated,
            "skipped_old": summary.skipped_old,
            "pages": summary.pages,
            "latest_published_at": latest,
            "rate_limited": summary.rate_limited,
            "http_errors": list(summary.http_errors),
        }

    job = get_registry().submit(stage="fetch", fn=_run)
    return _accepted(job)


@router.post(
    "/classify",
    status_code=status.HTTP_202_ACCEPTED,
)
def post_classify_job(payload: Annotated[DatePayload | None, Body()] = None) -> dict:
    payload = payload or DatePayload()
    target_date = _parse_date(payload.date)

    def _run(job: Job) -> dict:
        config = _resolve_config()
        engine = _build_engine()
        job.log.append(f"classify: target {target_date.isoformat()}")
        with session_scope(engine) as session:
            classified = run_classify(session, config, target_date)
        job.log.append(f"classify: {classified} item(s)")
        return {"classified": classified, "date": target_date.isoformat()}

    job = get_registry().submit(stage="classify", fn=_run)
    return _accepted(job)


@router.post(
    "/candidates",
    status_code=status.HTTP_202_ACCEPTED,
)
def post_candidates_job(payload: Annotated[DatePayload | None, Body()] = None) -> dict:
    payload = payload or DatePayload()
    target_date = _parse_date(payload.date)

    def _run(job: Job) -> dict:
        config = _resolve_config()
        engine = _build_engine()
        job.log.append(f"candidates: target {target_date.isoformat()}")
        with session_scope(engine) as session:
            summary = run_candidates(
                session,
                config,
                target_date,
                reports_dir=DefaultReportsDir,
                exports_dir=DefaultExportsDir,
            )
        job.log.append(f"candidates: {summary.count} written")
        return {
            "count": summary.count,
            "report_path": str(summary.report_path),
            "export_path": str(summary.export_path),
            "date": target_date.isoformat(),
        }

    job = get_registry().submit(stage="candidates", fn=_run)
    return _accepted(job)


@router.post(
    "/apply",
    status_code=status.HTTP_202_ACCEPTED,
)
def post_apply_job(payload: Annotated[ApplyPayload, Body()]) -> dict:
    markdown_path = Path(payload.markdown_path)

    def _run(job: Job) -> dict:
        engine = _build_engine()
        job.log.append(f"apply: {markdown_path}")
        try:
            with session_scope(engine) as session:
                report = run_apply(
                    session,
                    markdown_path,
                    decided_by=payload.decided_by,
                    dry_run=payload.dry_run,
                )
        except FileNotFoundError as exc:
            raise RuntimeError(str(exc)) from exc
        except ProposalParseError as exc:
            raise RuntimeError(str(exc)) from exc
        job.log.append(
            f"apply: applied={len(report.applied)} skipped={len(report.skipped)} "
            f"warnings={len(report.warnings)}"
        )
        return {
            "applied": len(report.applied),
            "skipped": len(report.skipped),
            "warnings": list(report.warnings),
            "dry_run": payload.dry_run,
            "markdown_path": str(markdown_path),
        }

    job = get_registry().submit(stage="apply", fn=_run)
    return _accepted(job)


@router.post(
    "/digest",
    status_code=status.HTTP_202_ACCEPTED,
)
def post_digest_job(payload: Annotated[DigestPayload | None, Body()] = None) -> dict:
    payload = payload or DigestPayload()
    target_date = _parse_date(payload.date)

    def _run(job: Job) -> dict:
        engine = _build_engine()
        job.log.append(f"digest: target {target_date.isoformat()} days={payload.days}")
        with session_scope(engine) as session:
            summary = run_digest(
                session,
                target_date,
                payload.days,
                reports_dir=DefaultDigestReportsDir,
                exports_dir=DefaultDigestExportsDir,
            )
        return {
            "count": summary.count,
            "report_path": str(summary.report_path),
            "export_path": str(summary.export_path),
            "date": target_date.isoformat(),
            "days": payload.days,
        }

    job = get_registry().submit(stage="digest", fn=_run)
    return _accepted(job)


@router.post(
    "/embed",
    status_code=status.HTTP_202_ACCEPTED,
)
def post_embed_job(payload: Annotated[DatePayload | None, Body()] = None) -> dict:
    payload = payload or DatePayload()
    target_date = _parse_date(payload.date)

    def _run(job: Job) -> dict:
        config = _resolve_config()
        engine = _build_engine()
        job.log.append(f"embed: target {target_date.isoformat()}")
        with session_scope(engine) as session:
            summary = run_embed(
                session,
                config.embeddings.embeddings,
                target_date,
            )
        return {
            "embedded": summary.embedded,
            "skipped": summary.skipped,
            "total": summary.total,
            "date": target_date.isoformat(),
        }

    job = get_registry().submit(stage="embed", fn=_run)
    return _accepted(job)


@router.post(
    "/relevance-check",
    status_code=status.HTTP_202_ACCEPTED,
)
def post_relevance_check_job(
    payload: Annotated[RelevancePayload | None, Body()] = None,
) -> dict:
    payload = payload or RelevancePayload()
    target_date = _parse_date(payload.date)

    def _run(job: Job) -> dict:
        config = _resolve_config()
        engine = _build_engine()
        job.log.append(f"relevance-check: target {target_date.isoformat()}")
        with session_scope(engine) as session:
            summary = run_relevance_check(
                session,
                config.embeddings.chat,
                target_date,
                limit=payload.limit,
                rejudge=payload.rejudge,
            )
        return {
            "judged": summary.judged,
            "skipped": summary.skipped,
            "failed": summary.failed,
            "yes_count": summary.yes_count,
            "no_count": summary.no_count,
            "unknown_count": summary.unknown_count,
            "total": summary.total,
            "date": target_date.isoformat(),
        }

    job = get_registry().submit(stage="relevance-check", fn=_run)
    return _accepted(job)


@router.post(
    "/daily-iteration",
    status_code=status.HTTP_202_ACCEPTED,
)
def post_daily_iteration_job(
    payload: Annotated[DailyIterationPayload | None, Body()] = None,
) -> dict:
    payload = payload or DailyIterationPayload()
    target_date = _parse_date(payload.date)
    fetch = payload.fetch

    def _run(job: Job) -> dict:
        config = _resolve_config()
        engine = _build_engine()
        with session_scope(engine) as session:
            job.log.append("daily-iteration: fetch starting")
            fetch_summary = run_fetch_arxiv(
                session,
                config,
                days=fetch.days,
                max_results=fetch.max_results,
                max_pages=fetch.max_pages,
                page_delay_seconds=fetch.page_delay_seconds,
            )
            job.log.append(
                f"daily-iteration: fetched={fetch_summary.fetched} stored={fetch_summary.stored}"
            )
            classified = run_classify(session, config, target_date)
            job.log.append(f"daily-iteration: classified {classified}")
            candidates_summary = run_candidates(
                session,
                config,
                target_date,
                reports_dir=DefaultReportsDir,
                exports_dir=DefaultExportsDir,
            )
            job.log.append(f"daily-iteration: {candidates_summary.count} candidate(s) written")
        result: dict = {
            "fetch": {
                "fetched": fetch_summary.fetched,
                "stored": fetch_summary.stored,
                "updated": fetch_summary.updated,
                "skipped_old": fetch_summary.skipped_old,
                "pages": fetch_summary.pages,
                "rate_limited": fetch_summary.rate_limited,
                "http_errors": list(fetch_summary.http_errors),
            },
            "classify": {"classified": classified, "date": target_date.isoformat()},
            "candidates": {
                "count": candidates_summary.count,
                "report_path": str(candidates_summary.report_path),
                "export_path": str(candidates_summary.export_path),
                "date": target_date.isoformat(),
            },
        }
        if fetch_summary.rate_limited:
            result["rate_limited"] = True
        return result

    job = get_registry().submit(stage="daily-iteration", fn=_run)
    return _accepted(job)


def _job_to_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "stage": job.stage,
        "state": job.state,
        "submitted_at": job.submitted_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "log": list(job.log),
        "error": job.error,
        "result": job.result,
    }


@router.get("/{job_id}")
def get_job(job_id: str) -> dict:
    # Mounted under "/jobs"; trailing-slash matches are folded by FastAPI.
    if job_id == "":
        raise HTTPException(status_code=404, detail="missing job id")
    job = get_registry().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job id: {job_id}")
    return _job_to_dict(job)


@router.get("")
def list_jobs(limit: Annotated[int, Query(ge=1, le=200)] = 20) -> dict:
    jobs = get_registry().recent(limit=limit)
    return {"jobs": [_job_to_dict(job) for job in jobs]}
