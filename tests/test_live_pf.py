"""Tests for live particle filter updater."""

import tempfile
from pathlib import Path

from polymarket_watcher.db import get_connection, init_db
from polymarket_watcher.engine.live_pf import LivePFUpdater


def test_live_pf_updater_estimate_in_range_and_snapshot_writes_to_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = get_connection(path)
        init_db(conn)
        conn.execute(
            "INSERT INTO markets (condition_id, slug, closed) VALUES ('0xc1', 'm1', 0)"
        )
        conn.commit()
        updater = LivePFUpdater("0xc1", prior_prob=0.5)
        for p in [0.45, 0.48, 0.52, 0.55, 0.58]:
            updater.on_tick(p)
        est = updater.get_estimate()
        assert 0 <= est <= 1
        updater.on_snapshot_interval(conn)
        cur = conn.execute(
            "SELECT condition_id, ts, estimate FROM pf_live_estimates WHERE condition_id = '0xc1'"
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "0xc1"
        assert 0 <= row[2] <= 1
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_live_pf_on_market_resolved_writes_run():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = get_connection(path)
        init_db(conn)
        updater = LivePFUpdater("0xc1")
        updater.on_tick(0.6)
        updater.on_market_resolved(conn, "Yes")
        cur = conn.execute(
            "SELECT condition_id, run_type, final_estimate, outcome FROM particle_filter_runs "
            "WHERE condition_id = '0xc1'"
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "0xc1"
        assert row[1] == "live"
        assert 0 <= row[2] <= 1
        assert row[3] == 1
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)
