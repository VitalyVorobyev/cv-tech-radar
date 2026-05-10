from __future__ import annotations

from sqlalchemy import inspect

from radar.db import get_engine, init_db


def test_init_db_creates_tables_and_is_idempotent(tmp_path):
    engine = get_engine(tmp_path / "radar.sqlite")
    init_db(engine)
    init_db(engine)
    tables = set(inspect(engine).get_table_names())
    assert {
        "sources",
        "raw_items",
        "items",
        "item_classifications",
        "radar_decisions",
        "digests",
    }.issubset(tables)
