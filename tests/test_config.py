from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from radar.config import ConfigError, load_app_config


def copy_config(tmp_path: Path) -> Path:
    target = tmp_path / "config"
    shutil.copytree("config", target)
    return target


def test_valid_config_loads(app_config):
    assert app_config.sources.sources[0].id == "arxiv-cs-cv"
    assert app_config.topics.tracks
    assert app_config.scoring.candidate_limit == 25
    assert not app_config.embeddings.embeddings.enabled


def test_duplicate_track_ids_fail(tmp_path):
    config_dir = copy_config(tmp_path)
    (config_dir / "topics.yaml").write_text(
        """
tracks:
  - id: duplicate
    name: One
    positive_keywords: [calibration]
  - id: duplicate
    name: Two
    positive_keywords: [stereo]
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_app_config(config_dir)


def test_bad_threshold_order_fails(tmp_path):
    config_dir = copy_config(tmp_path)
    (config_dir / "scoring.yaml").write_text(
        """
weights:
  relevance: 0.55
  source_priority: 0.10
  implementation: 0.10
  attention: 0.10
  novelty: 0.10
  negative_penalty: 0.15
thresholds:
  use: 50
  prototype: 80
  evaluate: 65
  watch: 45
  ignore: 0
source_priority_cap: 60
candidate_limit: 25
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_app_config(config_dir)


def test_missing_source_url_fails(tmp_path):
    config_dir = copy_config(tmp_path)
    (config_dir / "sources.yaml").write_text(
        """
sources:
  - id: arxiv-cs-cv
    name: arXiv cs.CV
    kind: arxiv
    enabled: true
    categories: [cs.CV]
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_app_config(config_dir)
