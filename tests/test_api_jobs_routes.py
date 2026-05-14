from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.db import session_scope
from radar.jobs import JobRegistry, set_registry
from radar.models import Item


@pytest.fixture
def jobs_client(tmp_path, app_config):
    from radar.db import ensure_sources, get_engine, init_db

    db_path = tmp_path / "api.sqlite"
    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        ensure_sources(session, app_config.sources)

    # Replace the singleton with a fresh registry so tests don't share state.
    registry = JobRegistry(max_workers=2)
    set_registry(registry)

    app = create_app(db_path=db_path, config_dir=Path("config"))
    with TestClient(app) as client:
        yield client, engine, registry

    registry.shutdown()
    set_registry(None)


def _wait_for(client: TestClient, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        if body["state"] in {"ok", "error", "rate_limited"}:
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


def _seed_item(session, *, item_id: int, title: str, published: datetime) -> None:
    session.add(
        Item(
            id=item_id,
            type="paper",
            title=title,
            normalized_title=title.casefold(),
            abstract_or_summary="Camera calibration with bundle adjustment for industrial cameras.",
            url=f"https://example.test/{item_id}",
            pdf_url=f"https://example.test/{item_id}.pdf",
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


def test_classify_job_accepts_and_runs(jobs_client):
    client, engine, _registry = jobs_client
    published = datetime(2026, 5, 11, 10, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(
            session,
            item_id=1,
            title="Subpixel checkerboard calibration",
            published=published,
        )

    response = client.post("/api/jobs/classify", json={"date": "2026-05-11"})
    assert response.status_code == 202
    body = response.json()
    assert body["state"] in {"queued", "running"}
    assert body["stage"] == "classify"
    assert isinstance(body["job_id"], str)

    final = _wait_for(client, body["job_id"])
    assert final["state"] == "ok"
    assert final["result"] is not None
    assert final["result"]["classified"] >= 1
    assert final["result"]["date"] == "2026-05-11"
    assert final["error"] is None
    assert final["started_at"] is not None
    assert final["finished_at"] is not None


def test_candidates_job_writes_outputs(jobs_client, tmp_path, monkeypatch):
    client, engine, _registry = jobs_client
    published = datetime(2026, 5, 11, 10, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(session, item_id=1, title="Subpixel calibration", published=published)

    # Run classify first via the API so the candidate row has a classification.
    classify_resp = client.post("/api/jobs/classify", json={"date": "2026-05-11"})
    _wait_for(client, classify_resp.json()["job_id"])

    # Redirect outputs into tmp dirs to keep the repo clean.
    reports_dir = tmp_path / "reports/candidates"
    exports_dir = tmp_path / "data/exports/candidates"
    monkeypatch.setattr("radar.api.routes.jobs.DefaultReportsDir", reports_dir)
    monkeypatch.setattr("radar.api.routes.jobs.DefaultExportsDir", exports_dir)

    response = client.post("/api/jobs/candidates", json={"date": "2026-05-11"})
    assert response.status_code == 202
    final = _wait_for(client, response.json()["job_id"])
    assert final["state"] == "ok"
    assert final["result"]["count"] >= 1
    assert Path(final["result"]["report_path"]).exists()
    assert Path(final["result"]["export_path"]).exists()


def test_get_unknown_job_returns_404(jobs_client):
    client, _engine, _registry = jobs_client
    response = client.get("/api/jobs/does-not-exist")
    assert response.status_code == 404


def test_list_jobs_returns_recent(jobs_client):
    client, _engine, _registry = jobs_client
    response = client.post("/api/jobs/classify", json={"date": "2026-05-11"})
    job_id = response.json()["job_id"]
    _wait_for(client, job_id)
    listed = client.get("/api/jobs", params={"limit": 5})
    assert listed.status_code == 200
    assert any(row["id"] == job_id for row in listed.json()["jobs"])


def test_score_debug_endpoint(jobs_client):
    client, engine, _registry = jobs_client
    published = datetime(2026, 5, 11, 10, tzinfo=UTC)
    with session_scope(engine) as session:
        _seed_item(
            session,
            item_id=1,
            title="Subpixel checkerboard calibration",
            published=published,
        )

    classify_resp = client.post("/api/jobs/classify", json={"date": "2026-05-11"})
    _wait_for(client, classify_resp.json()["job_id"])

    response = client.get("/api/score-debug", params={"date": "2026-05-11", "limit": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-05-11"
    assert len(body["items"]) >= 1
    row = body["items"][0]
    for key in (
        "item_id",
        "title",
        "ring",
        "final",
        "relevance",
        "source_priority",
        "implementation",
        "novelty",
        "negative_penalty",
        "tracks",
        "matched_keywords",
    ):
        assert key in row


def test_candidates_markdown_returns_exists_false_when_missing(jobs_client):
    client, _engine, _registry = jobs_client
    response = client.get("/api/candidates/markdown", params={"date": "2099-01-01"})
    assert response.status_code == 200
    body = response.json()
    assert body["exists"] is False
    assert body["markdown"] == ""
    assert body["mtime"] is None


def test_digest_markdown_returns_exists_false_when_missing(jobs_client):
    client, _engine, _registry = jobs_client
    response = client.get("/api/digest/markdown", params={"date": "2099-01-01"})
    assert response.status_code == 200
    body = response.json()
    assert body["exists"] is False
    assert body["markdown"] == ""
