from __future__ import annotations

from pathlib import Path

import pytest

from radar.config import load_app_config
from radar.db import ensure_sources, get_engine, init_db, session_scope


@pytest.fixture
def app_config():
    return load_app_config(Path("config"))


@pytest.fixture
def db_engine(tmp_path, app_config):
    engine = get_engine(tmp_path / "radar.sqlite")
    init_db(engine)
    with session_scope(engine) as session:
        ensure_sources(session, app_config.sources)
    return engine
