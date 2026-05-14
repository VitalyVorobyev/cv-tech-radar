from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from radar.api import deps as api_deps
from radar.config import load_app_config
from radar.config_io import (
    reload_config,
    write_negative_topics,
    write_scoring,
    write_sources,
    write_topics,
)
from radar.schemas import (
    NegativeTopicsConfig,
    ScoringConfig,
    SourcesConfig,
    TopicsConfig,
    TrackConfig,
)


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


def test_write_topics_round_trip_preserves_data(tmp_path):
    config_dir = _copy_real_config(tmp_path / "config")
    config = load_app_config(config_dir)
    topics_before = config.topics

    target = config_dir / "topics.yaml"
    write_topics(topics_before, path=target)

    config_after = load_app_config(config_dir)
    assert config_after.topics.model_dump() == topics_before.model_dump()


def test_write_topics_round_trip_preserves_comments_best_effort(tmp_path):
    config_dir = _copy_real_config(tmp_path / "config")
    config = load_app_config(config_dir)
    target = config_dir / "topics.yaml"
    write_topics(config.topics, path=target)
    text = target.read_text(encoding="utf-8")
    # The first track in topics.yaml has a multi-line block comment about why
    # bare `calibration` was removed. Comment preservation is best-effort, but
    # the round-trip path must keep it for the unchanged top-level shape.
    assert "false-positived" in text or "MLLM" in text


def test_write_topics_adds_new_keyword(tmp_path):
    config_dir = _copy_real_config(tmp_path / "config")
    config = load_app_config(config_dir)

    new_tracks = []
    for track in config.topics.tracks:
        if track.id == "calibration-camera-models":
            new_tracks.append(
                TrackConfig(
                    id=track.id,
                    name=track.name,
                    positive_keywords=[*track.positive_keywords, "vignetting calibration"],
                    negative_keywords=track.negative_keywords,
                )
            )
        else:
            new_tracks.append(track)
    updated = TopicsConfig(tracks=new_tracks)

    target = config_dir / "topics.yaml"
    write_topics(updated, path=target)

    reloaded = load_app_config(config_dir)
    cal = next(t for t in reloaded.topics.tracks if t.id == "calibration-camera-models")
    assert "vignetting calibration" in cal.positive_keywords


def test_invalid_topics_payload_is_rejected_before_io(tmp_path):
    config_dir = _copy_real_config(tmp_path / "config")
    target = config_dir / "topics.yaml"
    mtime_before = target.stat().st_mtime_ns

    with pytest.raises(ValidationError):
        # Duplicate track ids violate the model validator.
        TopicsConfig(
            tracks=[
                TrackConfig(id="dup", name="A", positive_keywords=["x"]),
                TrackConfig(id="dup", name="B", positive_keywords=["y"]),
            ]
        )

    # File must not have been touched.
    assert target.stat().st_mtime_ns == mtime_before


def test_write_sources_round_trip(tmp_path):
    config_dir = _copy_real_config(tmp_path / "config")
    config = load_app_config(config_dir)
    target = config_dir / "sources.yaml"
    write_sources(config.sources, path=target)
    reloaded = load_app_config(config_dir)
    assert reloaded.sources.model_dump() == config.sources.model_dump()


def test_write_negative_topics_round_trip(tmp_path):
    config_dir = _copy_real_config(tmp_path / "config")
    config = load_app_config(config_dir)
    target = config_dir / "negative_topics.yaml"
    updated = NegativeTopicsConfig(
        negative_topics=[*config.negative_topics.negative_topics, "indoor mapping"]
    )
    write_negative_topics(updated, path=target)
    reloaded = load_app_config(config_dir)
    assert "indoor mapping" in reloaded.negative_topics.negative_topics


def test_write_scoring_round_trip(tmp_path):
    config_dir = _copy_real_config(tmp_path / "config")
    config = load_app_config(config_dir)
    target = config_dir / "scoring.yaml"
    write_scoring(config.scoring, path=target)
    reloaded = load_app_config(config_dir)
    assert reloaded.scoring.model_dump() == config.scoring.model_dump()


def test_invalid_scoring_thresholds_rejected(tmp_path):
    with pytest.raises(ValidationError):
        # Thresholds must descend; this violates the rule.
        ScoringConfig.model_validate(
            {
                "weights": {
                    "relevance": 0.5,
                    "source_priority": 0.1,
                    "implementation": 0.1,
                    "attention": 0.1,
                    "novelty": 0.1,
                    "negative_penalty": 0.1,
                },
                "thresholds": {
                    "use": 50,
                    "prototype": 80,  # higher than use -> invalid
                    "evaluate": 65,
                    "watch": 45,
                    "ignore": 0,
                },
            }
        )


def test_invalid_sources_payload_rejected():
    with pytest.raises(ValidationError):
        SourcesConfig.model_validate(
            {
                "sources": [
                    {
                        "id": "dup",
                        "name": "A",
                        "kind": "arxiv",
                        "url": "https://example.com",
                        "categories": ["cs.CV"],
                    },
                    {
                        "id": "dup",
                        "name": "B",
                        "kind": "arxiv",
                        "url": "https://example.com",
                        "categories": ["cs.CV"],
                    },
                ]
            }
        )


def test_reload_config_clears_cache(tmp_path):
    config_dir = _copy_real_config(tmp_path / "config")
    api_deps.configure(db_path=tmp_path / "x.sqlite", config_dir=config_dir)
    # Prime the cache.
    _ = api_deps.get_config()
    assert api_deps.get_config.cache_info().currsize == 1
    reload_config()
    assert api_deps.get_config.cache_info().currsize == 0
