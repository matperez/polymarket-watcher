"""Tests for particle filter backtest job (engine)."""

import tempfile
from pathlib import Path

import pytest

from polymarket_watcher.db import get_connection, init_db
from polymarket_watcher.engine.pf_backtest import run_pf_backtest


def test_run_pf_backtest_inserts_run_with_final_estimate_and_outcome():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = get_connection(path)
        init_db(conn)
        conn.execute(
            """INSERT INTO markets (condition_id, slug, closed, resolution_outcome)
               VALUES ('0xc1', 'm1', 1, 'YES')"""
        )
        # Price series trending up (p from 0.3 to 0.7)
        for i in range(10):
            conn.execute(
                "INSERT INTO price_series (condition_id, t, p) VALUES ('0xc1', ?, ?)",
                (1700000000 + i * 3600, 0.3 + i * 0.04),
            )
        conn.commit()
        run_pf_backtest(conn)
        cur = conn.execute(
            """SELECT condition_id, run_type, final_estimate, outcome FROM particle_filter_runs
               WHERE condition_id = '0xc1'"""
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "0xc1"
        assert row[1] == "backtest"
        assert 0 <= row[2] <= 1
        assert row[3] == 1  # YES -> 1
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)
