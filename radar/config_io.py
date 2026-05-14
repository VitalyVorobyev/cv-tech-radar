"""Atomic, round-trip YAML writers for radar config files.

Each writer takes a validated Pydantic config (so structural / semantic
validation has already happened at the route boundary) and writes it back
to disk via ``ruamel.yaml`` to preserve comments and key order whenever
possible.

Comment preservation is best-effort: we load the existing file as a
``ruamel.yaml`` round-trip object, update its top-level fields in place,
and dump. If the file is missing, malformed, or its top-level shape no
longer matches the config (e.g. a list reshuffle), we fall back to a
fresh dump of the Pydantic data. The fallback loses comments but never
loses data.

Writes are atomic: we dump to a ``.tmp`` sibling, ``flush + fsync``, and
then ``os.replace`` onto the target — so a crash never leaves a
half-written config behind.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from radar.schemas import (
    NegativeTopicsConfig,
    ScoringConfig,
    SourcesConfig,
    TopicsConfig,
)

DEFAULT_CONFIG_DIR = Path("config")


def _yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    return yaml


def _load_existing(path: Path) -> Any | None:
    """Return the existing file as a ruamel round-trip object, or None."""
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return _yaml().load(handle)
    except Exception:
        return None


def _atomic_dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    buffer = io.StringIO()
    _yaml().dump(data, buffer)
    payload = buffer.getvalue()
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _merge_into_seq(target: Any, replacement: list[Any]) -> Any:
    """Best-effort: keep ``target`` (a CommentedSeq with comments) and
    align ``replacement`` to it element-by-element.

    When the existing sequence has the same length and shape, we recurse
    into matching positions so comments anchored inside individual list
    items (e.g. ``- id: foo`` with a block comment above ``positive_keywords:``)
    stay attached. When the shape changes, fall back to a wholesale
    replace — comments inside the affected items are lost but data is
    correct.
    """
    if not isinstance(target, CommentedSeq) or len(target) != len(replacement):
        new = CommentedSeq()
        new.extend(replacement)
        return new
    for index, new_item in enumerate(replacement):
        existing = target[index]
        if isinstance(existing, CommentedMap) and isinstance(new_item, dict):
            target[index] = _merge_into_map(existing, new_item)
        elif isinstance(existing, CommentedSeq) and isinstance(new_item, list):
            target[index] = _merge_into_seq(existing, new_item)
        else:
            target[index] = new_item
    return target


def _merge_into_map(target: Any, replacement: dict[str, Any]) -> Any:
    if not isinstance(target, CommentedMap):
        new = CommentedMap()
        new.update(replacement)
        return new
    # Update existing keys in place, add new keys, drop removed keys.
    for key in list(target.keys()):
        if key not in replacement:
            del target[key]
    for key, value in replacement.items():
        if key in target and isinstance(target[key], CommentedMap) and isinstance(value, dict):
            target[key] = _merge_into_map(target[key], value)
        elif key in target and isinstance(target[key], CommentedSeq) and isinstance(value, list):
            target[key] = _merge_into_seq(target[key], value)
        else:
            target[key] = value
    return target


def _resolved(default_name: str, override: Path | None) -> Path:
    if override is not None:
        return override
    return DEFAULT_CONFIG_DIR / default_name


def write_sources(
    sources_config: SourcesConfig,
    *,
    path: Path | None = None,
) -> Path:
    """Write a ``SourcesConfig`` to ``config/sources.yaml`` atomically."""
    target = _resolved("sources.yaml", path)
    data = sources_config.model_dump(mode="json")
    existing = _load_existing(target)
    merged = _merge_into_map(existing, data) if existing is not None else data
    _atomic_dump(target, merged)
    return target


def write_topics(
    topics_config: TopicsConfig,
    *,
    path: Path | None = None,
) -> Path:
    """Write a ``TopicsConfig`` to ``config/topics.yaml`` atomically."""
    target = _resolved("topics.yaml", path)
    data = topics_config.model_dump(mode="json")
    existing = _load_existing(target)
    merged = _merge_into_map(existing, data) if existing is not None else data
    _atomic_dump(target, merged)
    return target


def write_negative_topics(
    neg_config: NegativeTopicsConfig,
    *,
    path: Path | None = None,
) -> Path:
    """Write a ``NegativeTopicsConfig`` to ``config/negative_topics.yaml``."""
    target = _resolved("negative_topics.yaml", path)
    data = neg_config.model_dump(mode="json")
    existing = _load_existing(target)
    merged = _merge_into_map(existing, data) if existing is not None else data
    _atomic_dump(target, merged)
    return target


def write_scoring(
    scoring_config: ScoringConfig,
    *,
    path: Path | None = None,
) -> Path:
    """Write a ``ScoringConfig`` to ``config/scoring.yaml`` atomically."""
    target = _resolved("scoring.yaml", path)
    data = scoring_config.model_dump(mode="json")
    existing = _load_existing(target)
    merged = _merge_into_map(existing, data) if existing is not None else data
    _atomic_dump(target, merged)
    return target


def reload_config() -> None:
    """Clear cached config so the next request re-reads from disk."""
    # Local import to avoid a circular dependency at module load.
    from radar.api import deps as api_deps

    api_deps.get_config.cache_clear()


__all__ = [
    "reload_config",
    "write_negative_topics",
    "write_scoring",
    "write_sources",
    "write_topics",
]
