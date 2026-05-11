from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from radar.models import Base, Source
from radar.schemas import SourceConfig, SourcesConfig
from radar.utils import ensure_dir

DEFAULT_DB_PATH = Path("data/radar.sqlite")


def resolve_db_path(db_path: Path | str | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return Path(os.environ.get("CV_RADAR_DB_PATH", DEFAULT_DB_PATH))


def make_sqlite_url(db_path: Path | str | None = None) -> str:
    path = resolve_db_path(db_path)
    ensure_dir(path.parent)
    return f"sqlite:///{path}"


def get_engine(db_path: Path | str | None = None) -> Engine:
    return create_engine(make_sqlite_url(db_path), future=True)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ensure_sources(session: Session, config: SourcesConfig) -> None:
    for source_config in config.sources:
        upsert_source(session, source_config)


def upsert_source(session: Session, source_config: SourceConfig) -> Source:
    source = session.scalar(select(Source).where(Source.key == source_config.id))
    if source is None:
        source = Source(key=source_config.id, name=source_config.name, kind=source_config.kind)
        session.add(source)
    source.name = source_config.name
    source.kind = source_config.kind
    source.url = str(source_config.url)
    source.enabled = source_config.enabled
    source.priority = source_config.priority
    source.notes = source_config.notes
    return source
