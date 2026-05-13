"""In-memory job registry for asynchronous pipeline jobs.

The API exposes pipeline stages (fetch / classify / candidates / digest /
embed / relevance-check / daily-iteration) as fire-and-forget jobs that
the browser polls. This module provides a tiny ``JobRegistry`` backed by
a ``ThreadPoolExecutor`` so the API can return ``202 Accepted`` quickly
while long-running stages execute in the background.

The registry is intentionally in-memory: history disappears when the
process restarts. That matches the local-first deployment model and
avoids dragging Redis/Celery into the stack.

Threading contract: each job callback receives the ``Job`` it is running
under and *must* create its own SQLAlchemy ``Session`` inside the worker
thread. Sessions are not safe to share across threads.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

JobState = Literal["queued", "running", "ok", "error", "rate_limited"]

LOG_CAPACITY = 200


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Job:
    """Mutable record describing a single background job."""

    id: str
    stage: str
    state: JobState = "queued"
    submitted_at: datetime = field(default_factory=_utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    log: deque[str] = field(default_factory=lambda: deque(maxlen=LOG_CAPACITY))
    error: str | None = None
    result: dict | None = None


JobFn = Callable[[Job], dict | None]


class JobRegistry:
    """Thread-safe registry of jobs plus the executor that runs them."""

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="cv-radar-job",
        )
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, *, stage: str, fn: JobFn) -> Job:
        job = Job(id=uuid.uuid4().hex, stage=stage)
        with self._lock:
            self._jobs[job.id] = job
        self._executor.submit(self._run, job, fn)
        return job

    def _run(self, job: Job, fn: JobFn) -> None:
        with self._lock:
            job.state = "running"
            job.started_at = _utc_now()
        try:
            result = fn(job) or {}
        except Exception as exc:  # noqa: BLE001 - we forward the message verbatim
            with self._lock:
                job.state = "error"
                job.error = f"{type(exc).__name__}: {exc}"
                job.finished_at = _utc_now()
                tb = traceback.format_exc().strip().splitlines()
                # Cap traceback inside the log; full text is in `error`.
                for line in tb[-10:]:
                    job.log.append(line)
            return
        with self._lock:
            job.result = result
            if isinstance(result, dict) and result.get("rate_limited"):
                job.state = "rate_limited"
            else:
                job.state = "ok"
            job.finished_at = _utc_now()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def recent(self, limit: int = 20) -> list[Job]:
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda job: job.submitted_at, reverse=True)
        return jobs[:limit]

    def log_line(self, job_id: str, line: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.log.append(line)

    def wait_for(self, job_id: str, timeout: float = 5.0) -> Job | None:
        """Block until the job reaches a terminal state, for tests.

        Polls every 10 ms. Returns the job (whatever state it is in) or
        ``None`` if the job id is unknown.
        """
        deadline = _utc_now().timestamp() + timeout
        while True:
            job = self.get(job_id)
            if job is None:
                return None
            if job.state in {"ok", "error", "rate_limited"}:
                return job
            if _utc_now().timestamp() >= deadline:
                return job
            threading.Event().wait(0.01)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    # exposed mostly for tests that need to inspect underlying futures
    def _executor_for_test(self) -> ThreadPoolExecutor:
        return self._executor


_registry: JobRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> JobRegistry:
    """Return the process-wide singleton ``JobRegistry``."""
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = JobRegistry()
        return _registry


def set_registry(registry: JobRegistry | None) -> None:
    """Override the singleton (tests only)."""
    global _registry
    with _registry_lock:
        _registry = registry


__all__ = [
    "Future",
    "Job",
    "JobFn",
    "JobRegistry",
    "JobState",
    "get_registry",
    "set_registry",
]
