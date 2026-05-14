"""Tests for the manual paper-add endpoint."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from radar.api.app import create_app
from radar.db import get_engine, session_scope
from radar.models import Item, ItemClassification, Source


def _copy_real_config(dst: Path) -> Path:
    src = Path("config")
    dst.mkdir(parents=True, exist_ok=True)
    for name in (
        "sources.yaml",
        "topics.yaml",
        "negative_topics.yaml",
        "priority_sources.yaml",
        "scoring.yaml",
        "embeddings.yaml",
    ):
        shutil.copy(src / name, dst / name)
    return dst


@pytest.fixture
def manual_client(tmp_path):
    config_dir = _copy_real_config(tmp_path / "config")
    db_path = tmp_path / "api.sqlite"
    app = create_app(db_path=db_path, config_dir=config_dir)
    with TestClient(app) as client:
        yield client, db_path


def _payload(**overrides) -> dict:
    base = {
        "title": "Industrial Camera Calibration with Bundle Adjustment for Subpixel Targets",
        "url": "https://example.test/paper-1",
        "abstract": (
            "We present a multi-camera bundle adjustment pipeline for industrial "
            "metrology, with subpixel target detection and stereo geometry."
        ),
        "published_at": "2026-05-12T10:00:00+00:00",
        "authors": ["Alice", "Bob"],
        "pdf_url": "https://example.test/paper-1.pdf",
        "doi": None,
        "external_id": None,
        "item_type": "paper",
    }
    base.update(overrides)
    return base


def test_post_manual_creates_classified_item(manual_client):
    client, db_path = manual_client

    response = client.post("/api/items/manual", json=_payload())
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["created"] is True
    assert body["item_id"] > 0
    assert isinstance(body["tracks"], list)
    assert body["recommended_ring"] in {"Use", "Prototype", "Evaluate", "Watch", "Ignore"}
    assert "Calibration & Camera Models" in body["tracks"]

    engine = get_engine(db_path)
    with session_scope(engine) as session:
        item = session.get(Item, body["item_id"])
        assert item is not None
        assert item.source_name == "Manual"
        classification = session.scalar(
            select(ItemClassification).where(ItemClassification.item_id == item.id)
        )
        assert classification is not None
        valid_rings = {"Use", "Prototype", "Evaluate", "Watch", "Ignore"}
        assert classification.recommended_ring in valid_rings


def test_post_manual_surfaces_in_queue(manual_client):
    client, _ = manual_client
    response = client.post("/api/items/manual", json=_payload())
    assert response.status_code == 201
    item_id = response.json()["item_id"]

    queue = client.get("/api/queue", params={"date": "2026-05-12"})
    assert queue.status_code == 200
    ids = [c["id"] for c in queue.json()["candidates"]]
    assert item_id in ids


def test_post_manual_dedups_on_url(manual_client):
    client, _ = manual_client
    first = client.post("/api/items/manual", json=_payload())
    assert first.status_code == 201
    first_id = first.json()["item_id"]

    second = client.post(
        "/api/items/manual",
        json=_payload(
            title="Industrial Camera Calibration with Bundle Adjustment for Subpixel Targets v2",
            abstract="Slightly revised abstract.",
        ),
    )
    assert second.status_code == 201
    assert second.json()["item_id"] == first_id
    assert second.json()["created"] is False


def test_post_manual_rejects_blank_title(manual_client):
    client, _ = manual_client
    response = client.post("/api/items/manual", json=_payload(title=""))
    assert response.status_code == 422


def test_post_manual_rejects_unknown_field(manual_client):
    client, _ = manual_client
    payload = _payload()
    payload["totally_made_up"] = "nope"
    response = client.post("/api/items/manual", json=payload)
    assert response.status_code == 422


def test_post_manual_bootstraps_source_row(manual_client):
    client, db_path = manual_client
    response = client.post("/api/items/manual", json=_payload())
    assert response.status_code == 201

    engine = get_engine(db_path)
    with session_scope(engine) as session:
        source = session.scalar(select(Source).where(Source.key == "manual"))
        assert source is not None
        assert source.kind == "manual"
        assert source.enabled is True


def test_manual_payload_accepts_minimum_fields(manual_client):
    client, _ = manual_client
    response = client.post(
        "/api/items/manual",
        json={
            "title": "Quick Paper",
            "url": "https://example.test/minimal",
            "published_at": datetime(2026, 5, 12, 10, tzinfo=UTC).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] is True
    assert isinstance(body["final_score"], float)
