from __future__ import annotations

from radar.jobs import JobRegistry


def test_job_registry_runs_callback_and_records_log():
    registry = JobRegistry(max_workers=2)

    def fn(job):
        job.log.append("hello")
        return {"value": 42}

    job = registry.submit(stage="test", fn=fn)
    final = registry.wait_for(job.id, timeout=5.0)
    assert final is not None
    assert final.state == "ok"
    assert final.started_at is not None
    assert final.finished_at is not None
    assert "hello" in final.log
    assert final.result == {"value": 42}
    registry.shutdown()


def test_job_registry_captures_exception_as_error_state():
    registry = JobRegistry(max_workers=1)

    def fn(_job):
        raise ValueError("boom")

    job = registry.submit(stage="test", fn=fn)
    final = registry.wait_for(job.id, timeout=5.0)
    assert final is not None
    assert final.state == "error"
    assert final.error is not None
    assert "boom" in final.error
    registry.shutdown()


def test_job_registry_rate_limited_state():
    registry = JobRegistry(max_workers=1)

    def fn(_job):
        return {"rate_limited": True, "http_errors": [429]}

    job = registry.submit(stage="fetch", fn=fn)
    final = registry.wait_for(job.id, timeout=5.0)
    assert final is not None
    assert final.state == "rate_limited"
    assert final.result is not None
    assert final.result["rate_limited"] is True
    registry.shutdown()


def test_job_registry_recent_orders_newest_first():
    registry = JobRegistry(max_workers=1)
    first = registry.submit(stage="a", fn=lambda _j: {"i": 1})
    registry.wait_for(first.id, timeout=5.0)
    second = registry.submit(stage="b", fn=lambda _j: {"i": 2})
    registry.wait_for(second.id, timeout=5.0)
    recent = registry.recent(limit=10)
    assert [j.id for j in recent[:2]] == [second.id, first.id]
    registry.shutdown()


def test_job_registry_get_unknown_returns_none():
    registry = JobRegistry(max_workers=1)
    assert registry.get("no-such-id") is None
    registry.shutdown()


def test_job_log_capped_at_capacity():
    registry = JobRegistry(max_workers=1)

    def fn(job):
        for index in range(500):
            job.log.append(f"line-{index}")
        return {"lines": 500}

    job = registry.submit(stage="noisy", fn=fn)
    final = registry.wait_for(job.id, timeout=5.0)
    assert final is not None
    assert final.state == "ok"
    # Capped at 200; oldest lines dropped.
    assert len(final.log) == 200
    assert "line-499" in final.log
    assert "line-0" not in final.log
    registry.shutdown()
