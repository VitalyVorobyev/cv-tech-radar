from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, select, text
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
    return create_engine(
        make_sqlite_url(db_path),
        future=True,
        connect_args={"check_same_thread": False},
    )


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    ensure_radar_decision_columns(engine)
    ensure_digest_columns(engine)
    ensure_movement_columns(engine)
    ensure_review_gate_columns(engine)


def ensure_radar_decision_columns(engine: Engine) -> None:
    with engine.begin() as connection:
        columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info('radar_decisions')"))
        }
        if "uncertain" not in columns:
            connection.execute(
                text("ALTER TABLE radar_decisions ADD COLUMN uncertain BOOLEAN NOT NULL DEFAULT 0")
            )


def ensure_digest_columns(engine: Engine) -> None:
    with engine.begin() as connection:
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info('digests')"))}
        if "updated_at" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE digests "
                    "ADD COLUMN updated_at DATETIME NOT NULL "
                    "DEFAULT CURRENT_TIMESTAMP"
                )
            )


def ensure_movement_columns(engine: Engine) -> None:
    """Add previous_ring on radar_decisions and first_decided_at on items; backfill once."""
    with engine.begin() as connection:
        decision_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info('radar_decisions')"))
        }
        item_columns = {row[1] for row in connection.execute(text("PRAGMA table_info('items')"))}

        if "previous_ring" not in decision_columns:
            connection.execute(text("ALTER TABLE radar_decisions ADD COLUMN previous_ring TEXT"))
            connection.execute(
                text(
                    """
                    WITH ranked AS (
                        SELECT id,
                               LAG(ring) OVER (
                                   PARTITION BY item_id ORDER BY created_at, id
                               ) AS prev_ring
                        FROM radar_decisions
                    )
                    UPDATE radar_decisions
                    SET previous_ring = (
                        SELECT prev_ring FROM ranked WHERE ranked.id = radar_decisions.id
                    )
                    WHERE previous_ring IS NULL
                    """
                )
            )

        if "first_decided_at" not in item_columns:
            connection.execute(text("ALTER TABLE items ADD COLUMN first_decided_at DATETIME"))
            connection.execute(
                text(
                    """
                    UPDATE items
                    SET first_decided_at = (
                        SELECT MIN(created_at)
                        FROM radar_decisions
                        WHERE radar_decisions.item_id = items.id
                    )
                    WHERE first_decided_at IS NULL
                    """
                )
            )


# Tables that carry a curator ring and therefore need the manual gate.
_GATED_DECISION_TABLES = (
    ("radar_decisions", "items", "item_id"),
    ("artifact_decisions", "artifacts", "artifact_id"),
)

# decided_by values that were already a person clicking in the web UI. Every
# other historical writer (claude-curator, codex, seed-script) was an agent.
_HUMAN_DECIDED_BY = ("web-curator", "curator", "ui-curator")

# The one-time cleanup: only these rings survive the gate unreviewed. Every
# other pre-existing decision becomes a pending proposal.
_GRANDFATHERED_RINGS = ("Use", "Prototype")

_BACKFILL_CONFIRMED_BY = "backfill-manual-gate"


def ensure_review_gate_columns(engine: Engine) -> None:
    """Add the manual-gate columns to both decision tables; backfill once.

    ``confirmed_at IS NOT NULL`` is what puts an item on the radar. Adding the
    columns to an existing database would therefore hide everything, so the
    same migration performs the agreed one-time cleanup: the latest decision
    per entity is grandfathered in only when its ring is Use or Prototype.
    Nothing is deleted — the Ignore corpus that scoring A/B work depends on is
    kept, just unconfirmed.
    """
    with engine.begin() as connection:
        for table, parent_table, fk_column in _GATED_DECISION_TABLES:
            columns = {row[1] for row in connection.execute(text(f"PRAGMA table_info('{table}')"))}
            if "origin" in columns:
                continue  # already migrated; the backfill below must not re-run

            connection.execute(
                text(f"ALTER TABLE {table} ADD COLUMN origin TEXT NOT NULL DEFAULT 'agent'")
            )
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN confirmed_at DATETIME"))
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN confirmed_by TEXT"))

            placeholders = ", ".join(f":human{i}" for i in range(len(_HUMAN_DECIDED_BY)))
            connection.execute(
                text(f"UPDATE {table} SET origin = 'human' WHERE decided_by IN ({placeholders})"),
                {f"human{i}": value for i, value in enumerate(_HUMAN_DECIDED_BY)},
            )

            # Grandfather the latest decision per entity when it is Use or
            # Prototype. "Latest" uses the same max(created_at) -> max(id)
            # tiebreak as every read site, so the confirmed row is exactly the
            # one the board would have shown.
            rings = ", ".join(f":ring{i}" for i in range(len(_GRANDFATHERED_RINGS)))
            connection.execute(
                text(
                    f"""
                    WITH latest AS (
                        SELECT id, ring,
                               ROW_NUMBER() OVER (
                                   PARTITION BY {fk_column}
                                   ORDER BY created_at DESC, id DESC
                               ) AS rn
                        FROM {table}
                    )
                    UPDATE {table}
                    SET confirmed_at = created_at,
                        confirmed_by = :confirmed_by,
                        origin = 'human'
                    WHERE id IN (
                        SELECT id FROM latest WHERE rn = 1 AND ring IN ({rings})
                    )
                    """
                ),
                {
                    "confirmed_by": _BACKFILL_CONFIRMED_BY,
                    **{f"ring{i}": value for i, value in enumerate(_GRANDFATHERED_RINGS)},
                },
            )

            # first_decided_at now means "first *confirmed* decision", so it
            # has to be rebuilt rather than left at the old proposal times.
            connection.execute(
                text(
                    f"""
                    UPDATE {parent_table}
                    SET first_decided_at = (
                        SELECT MIN(confirmed_at) FROM {table}
                        WHERE {table}.{fk_column} = {parent_table}.id
                          AND {table}.confirmed_at IS NOT NULL
                    )
                    """
                )
            )


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
