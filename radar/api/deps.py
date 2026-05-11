from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from radar.config import load_app_config
from radar.db import ensure_sources, get_engine, init_db, session_scope
from radar.schemas import AppConfig


@dataclass
class Settings:
    db_path: Path | None = None
    config_dir: Path | None = None


_settings = Settings()


def configure(db_path: Path | None, config_dir: Path | None) -> None:
    """Set process-wide API settings.

    Called by ``create_app`` so that dependency functions can resolve the
    correct database and config directory without each request rebuilding
    them.
    """
    _settings.db_path = db_path
    _settings.config_dir = config_dir
    get_engine_dep.cache_clear()
    get_config.cache_clear()


def get_settings() -> Settings:
    return _settings


@lru_cache(maxsize=1)
def get_engine_dep() -> Engine:
    engine = get_engine(_settings.db_path)
    init_db(engine)
    config = get_config()
    with session_scope(engine) as session:
        ensure_sources(session, config.sources)
    return engine


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    config_dir = _settings.config_dir or Path("config")
    return load_app_config(config_dir)


def get_session(engine: Annotated[Engine, Depends(get_engine_dep)]) -> Iterator[Session]:
    with session_scope(engine) as session:
        yield session
