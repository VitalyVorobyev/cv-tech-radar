from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.config import load_app_config


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
def cfg_client(tmp_path):
    config_dir = _copy_real_config(tmp_path / "config")
    db_path = tmp_path / "api.sqlite"
    app = create_app(db_path=db_path, config_dir=config_dir)
    with TestClient(app) as client:
        yield client, config_dir


def test_get_topics_matches_config_file(cfg_client):
    client, config_dir = cfg_client
    response = client.get("/api/config/topics")
    assert response.status_code == 200
    expected = load_app_config(config_dir).topics.model_dump(mode="json")
    assert response.json() == expected


def test_put_topics_persists_change(cfg_client):
    client, config_dir = cfg_client

    payload = load_app_config(config_dir).topics.model_dump()
    for track in payload["tracks"]:
        if track["id"] == "calibration-camera-models":
            track["positive_keywords"].append("vignetting calibration")
            break

    response = client.put("/api/config/topics", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["path"].endswith("topics.yaml")
    assert "saved_at" in body

    reloaded = load_app_config(config_dir)
    cal = next(t for t in reloaded.topics.tracks if t.id == "calibration-camera-models")
    assert "vignetting calibration" in cal.positive_keywords

    # GET after PUT reflects the change.
    fresh = client.get("/api/config/topics").json()
    cal_fresh = next(t for t in fresh["tracks"] if t["id"] == "calibration-camera-models")
    assert "vignetting calibration" in cal_fresh["positive_keywords"]


def test_put_topics_invalid_payload_returns_422_and_keeps_file(cfg_client):
    client, config_dir = cfg_client
    target = config_dir / "topics.yaml"
    mtime_before = target.stat().st_mtime_ns

    bad_payload = {
        "tracks": [
            {"id": "dup", "name": "A", "positive_keywords": ["x"]},
            {"id": "dup", "name": "B", "positive_keywords": ["y"]},
        ]
    }
    response = client.put("/api/config/topics", json=bad_payload)
    assert response.status_code == 422
    assert target.stat().st_mtime_ns == mtime_before


def test_get_sources_returns_current_config(cfg_client):
    client, config_dir = cfg_client
    response = client.get("/api/config/sources")
    assert response.status_code == 200
    expected = load_app_config(config_dir).sources.model_dump(mode="json")
    # Pydantic serializes HttpUrl into a string; both sides go through model_dump.
    assert response.json() == expected


def test_put_negative_topics_adds_entry(cfg_client):
    client, config_dir = cfg_client
    current = load_app_config(config_dir).negative_topics.model_dump()
    current["negative_topics"].append("indoor mapping")
    response = client.put("/api/config/negative-topics", json=current)
    assert response.status_code == 200, response.text

    reloaded = load_app_config(config_dir)
    assert "indoor mapping" in reloaded.negative_topics.negative_topics


def test_put_scoring_round_trip(cfg_client):
    client, config_dir = cfg_client
    current = load_app_config(config_dir).scoring.model_dump()
    response = client.put("/api/config/scoring", json=current)
    assert response.status_code == 200, response.text
    reloaded = load_app_config(config_dir).scoring.model_dump()
    assert reloaded == current


def test_post_reload_returns_timestamp(cfg_client):
    client, _ = cfg_client
    response = client.post("/api/config/reload")
    assert response.status_code == 200
    assert "reloaded_at" in response.json()
