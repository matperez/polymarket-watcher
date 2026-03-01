"""Tests for Brier aggregate job (engine)."""

import tempfile
from pathlib import Path

import pytest

from polymarket_watcher.db import get_connection, init_db
from polymarket_watcher.engine.brier import compute_brier_aggregate


def test_compute_brier_aggregate_inserts_row_with_correct_score():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = get_connection(path)
        init_db(conn)
        # 3 markets: resolution YES, NO, YES -> outcomes 1, 0, 1
        conn.executemany(
            """INSERT INTO markets (condition_id, slug, closed, resolution_outcome)
               VALUES (?, ?, 1, ?)""",
            [("c1", "m1", "YES"), ("c2", "m2", "NO"), ("c3", "m3", "YES")],
        )
        # Snapshots: prices 0.6, 0.4, 0.8
        conn.executemany(
            """INSERT INTO price_snapshots (condition_id, snapshot_at_ts, price, source)
               VALUES (?, 1700000000, ?, 'midpoint')""",
            [("c1", 0.6), ("c2", 0.4), ("c3", 0.8)],
        )
        conn.commit()
        compute_brier_aggregate(conn)
        cur = conn.execute(
            "SELECT period, n_markets, brier_score FROM brier_aggregates"
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "all"
        assert row[1] == 3
        # Brier = mean((0.6-1)^2, (0.4-0)^2, (0.8-1)^2) = mean(0.16, 0.16, 0.04) = 0.12
        assert abs(row[2] - 0.12) < 1e-6
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)
