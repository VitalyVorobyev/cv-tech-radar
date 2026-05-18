from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from radar.schemas import (
    AppConfig,
    ArtifactsConfig,
    EmbeddingsConfig,
    NegativeTopicsConfig,
    PrioritySourcesConfig,
    ScoringConfig,
    SourcesConfig,
    TopicsConfig,
)


class ConfigError(RuntimeError):
    pass


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        msg = f"Missing config file: {path}"
        raise ConfigError(msg)
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        msg = f"Config file must contain a YAML mapping: {path}"
        raise ConfigError(msg)
    return data


def _read_yaml_optional(path: Path) -> dict[str, Any]:
    """Read a YAML mapping, returning {} when the file is absent.

    Used for optional config files (e.g. artifacts.yaml) so deployments that
    predate the file keep loading unchanged.
    """
    if not path.exists():
        return {}
    return _read_yaml(path)


def load_app_config(config_dir: Path | str = "config") -> AppConfig:
    root = Path(config_dir)
    try:
        return AppConfig(
            sources=SourcesConfig.model_validate(_read_yaml(root / "sources.yaml")),
            topics=TopicsConfig.model_validate(_read_yaml(root / "topics.yaml")),
            negative_topics=NegativeTopicsConfig.model_validate(
                _read_yaml(root / "negative_topics.yaml")
            ),
            priority_sources=PrioritySourcesConfig.model_validate(
                _read_yaml(root / "priority_sources.yaml")
            ),
            scoring=ScoringConfig.model_validate(_read_yaml(root / "scoring.yaml")),
            embeddings=EmbeddingsConfig.model_validate(_read_yaml(root / "embeddings.yaml")),
            artifacts=ArtifactsConfig.model_validate(_read_yaml_optional(root / "artifacts.yaml")),
        )
    except ValidationError as exc:
        msg = f"Invalid radar configuration in {root}: {exc}"
        raise ConfigError(msg) from exc
