"""Tests for DB init and basic operations."""

import tempfile
from pathlib import Path

from polymarket_watcher.db import get_connection, init_db


def test_init_db_creates_tables_and_insert_select_works():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = get_connection(path)
        init_db(conn)
        conn.execute(
            "INSERT INTO markets (condition_id, slug, closed) VALUES (?, ?, ?)",
            ("0xabc", "test-market", 0),
        )
        conn.commit()
        cur = conn.execute("SELECT COUNT(*) FROM markets")
        assert cur.fetchone()[0] == 1
        conn.execute(
            "INSERT INTO watched_markets (condition_id, token_id_yes, slug, created_at)"
            " VALUES (?, ?, ?, ?)",
            ("0xc1", "tok1", "slug1", 1700000000),
        )
        conn.commit()
        cur = conn.execute("SELECT * FROM watched_markets")
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "0xc1"
        assert rows[0][2] == "tok1"
        assert rows[0][3] == "slug1"
        assert rows[0][4] == 1700000000
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)
