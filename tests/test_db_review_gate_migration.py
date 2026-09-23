"""Migration coverage for the manual review gate.

`init_db` is the whole migration system here (no Alembic), and the gate
migration is the first one that changes what an existing database *shows* —
so it is worth pinning precisely. It builds a pre-migration schema by hand,
runs `init_db`, and checks the one-time cleanup.
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from radar.db import get_engine, init_db

# The radar_decisions / artifact_decisions shape as it was before the gate.
_PRE_GATE_DECISIONS = """
CREATE TABLE radar_decisions (
    id INTEGER NOT NULL PRIMARY KEY,
    item_id INTEGER NOT NULL,
    ring VARCHAR(40) NOT NULL,
    tracks_json JSON,
    decision_reason TEXT,
    action TEXT,
    decided_by VARCHAR(120),
    uncertain BOOLEAN NOT NULL DEFAULT 0,
    previous_ring VARCHAR(40),
    created_at DATETIME NOT NULL
)
"""
_PRE_GATE_ITEMS = """
CREATE TABLE items (
    id INTEGER NOT NULL PRIMARY KEY,
    type VARCHAR(80),
    title TEXT,
    normalized_title TEXT,
    abstract_or_summary TEXT,
    url TEXT,
    pdf_url TEXT,
    published_at DATETIME,
    updated_at DATETIME,
    source_name VARCHAR(240),
    external_id VARCHAR(240),
    doi VARCHAR(240),
    arxiv_id VARCHAR(120),
    authors_json JSON,
    organizations_json JSON,
    metadata_json JSON,
    created_at DATETIME,
    first_decided_at DATETIME
)
"""


def _columns(engine, table: str) -> set[str]:
    with engine.begin() as conn:
        return {row[1] for row in conn.execute(text(f"PRAGMA table_info('{table}')"))}


def _seed_pre_gate(engine, rows: list[tuple[int, int, str, str]]) -> None:
    """rows: (decision_id, item_id, ring, decided_by), ordered oldest first."""
    with engine.begin() as conn:
        conn.execute(text(_PRE_GATE_ITEMS))
        conn.execute(text(_PRE_GATE_DECISIONS))
        for item_id in sorted({row[1] for row in rows}):
            conn.execute(
                text("INSERT INTO items (id, title, created_at) VALUES (:i, :t, '2026-01-01')"),
                {"i": item_id, "t": f"item {item_id}"},
            )
        for index, (decision_id, item_id, ring, decided_by) in enumerate(rows):
            conn.execute(
                text(
                    "INSERT INTO radar_decisions "
                    "(id, item_id, ring, decided_by, created_at, uncertain) "
                    "VALUES (:d, :i, :r, :b, :c, 0)"
                ),
                {
                    "d": decision_id,
                    "i": item_id,
                    "r": ring,
                    "b": decided_by,
                    "c": f"2026-05-{index + 1:02d} 10:00:00",
                },
            )


def test_migration_adds_gate_columns_to_both_tables(tmp_path):
    engine = get_engine(tmp_path / "radar.sqlite")
    init_db(engine)
    for table in ("radar_decisions", "artifact_decisions"):
        assert {"origin", "confirmed_at", "confirmed_by"}.issubset(_columns(engine, table))
    assert "review" not in set(inspect(engine).get_table_names())  # no new table needed


def test_migration_confirms_only_use_and_prototype(tmp_path):
    """The agreed one-time cleanup: everything else becomes a pending proposal."""
    engine = get_engine(tmp_path / "radar.sqlite")
    _seed_pre_gate(
        engine,
        [
            (1, 10, "Use", "claude-curator"),
            (2, 20, "Prototype", "claude-curator"),
            (3, 30, "Evaluate", "claude-curator"),
            (4, 40, "Watch", "claude-curator"),
            (5, 50, "Ignore", "claude-curator"),
        ],
    )
    init_db(engine)

    with engine.begin() as conn:
        confirmed = {
            row[0]
            for row in conn.execute(
                text("SELECT ring FROM radar_decisions WHERE confirmed_at IS NOT NULL")
            )
        }
        pending = {
            row[0]
            for row in conn.execute(
                text("SELECT ring FROM radar_decisions WHERE confirmed_at IS NULL")
            )
        }
        total = conn.execute(text("SELECT COUNT(*) FROM radar_decisions")).scalar()

    assert confirmed == {"Use", "Prototype"}
    assert pending == {"Evaluate", "Watch", "Ignore"}
    # Nothing is deleted — the Ignore corpus that scoring work depends on stays.
    assert total == 5


def test_migration_grandfathers_only_the_latest_decision_per_item(tmp_path):
    """An item promoted to Use and later demoted to Watch must stay off the radar."""
    engine = get_engine(tmp_path / "radar.sqlite")
    _seed_pre_gate(
        engine,
        [
            (1, 10, "Use", "claude-curator"),  # older
            (2, 10, "Watch", "claude-curator"),  # latest -> not grandfathered
            (3, 20, "Watch", "claude-curator"),  # older
            (4, 20, "Prototype", "claude-curator"),  # latest -> grandfathered
        ],
    )
    init_db(engine)

    with engine.begin() as conn:
        rows = dict(
            conn.execute(
                text("SELECT id, confirmed_at IS NOT NULL FROM radar_decisions ORDER BY id")
            ).all()
        )
    assert rows == {1: 0, 2: 0, 3: 0, 4: 1}


def test_migration_backfills_origin_from_decided_by(tmp_path):
    engine = get_engine(tmp_path / "radar.sqlite")
    _seed_pre_gate(
        engine,
        [
            (1, 10, "Watch", "claude-curator"),
            (2, 20, "Watch", "codex"),
            (3, 30, "Watch", "web-curator"),
            (4, 40, "Watch", "curator"),
        ],
    )
    init_db(engine)

    with engine.begin() as conn:
        origins = dict(conn.execute(text("SELECT decided_by, origin FROM radar_decisions")).all())
    assert origins == {
        "claude-curator": "agent",
        "codex": "agent",
        "web-curator": "human",
        "curator": "human",
    }


def test_migration_rebuilds_first_decided_at_from_confirmations(tmp_path):
    engine = get_engine(tmp_path / "radar.sqlite")
    _seed_pre_gate(
        engine,
        [
            (1, 10, "Use", "claude-curator"),  # confirmed -> stamps item 10
            (2, 20, "Watch", "claude-curator"),  # pending -> item 20 stays NULL
        ],
    )
    with engine.begin() as conn:
        # Pre-gate, both items looked "decided".
        conn.execute(text("UPDATE items SET first_decided_at = '2026-05-01 10:00:00'"))
    init_db(engine)

    with engine.begin() as conn:
        stamps = dict(conn.execute(text("SELECT id, first_decided_at FROM items")).all())
    assert stamps[10] is not None
    assert stamps[20] is None


def test_migration_is_idempotent_and_does_not_reconfirm(tmp_path):
    """A second run must not re-grandfather a decision the curator un-confirmed."""
    engine = get_engine(tmp_path / "radar.sqlite")
    _seed_pre_gate(engine, [(1, 10, "Use", "claude-curator")])
    init_db(engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE radar_decisions SET confirmed_at = NULL WHERE id = 1"))

    init_db(engine)

    with engine.begin() as conn:
        still_null = conn.execute(
            text("SELECT confirmed_at FROM radar_decisions WHERE id = 1")
        ).scalar()
    assert still_null is None
