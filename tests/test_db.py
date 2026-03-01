"""Tests for DB init and basic operations."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

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
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)
