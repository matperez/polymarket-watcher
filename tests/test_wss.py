"""Tests for WebSocket message parsing and DB writers."""

import tempfile
from pathlib import Path

from polymarket_watcher.db import get_connection, init_db
from polymarket_watcher.ingestion.wss import (
    _parse_resolved,
    _parse_tick,
    write_resolved_to_db,
    write_tick_to_db,
)


def test_parse_tick_last_trade_price():
    msg = {"event_type": "last_trade_price", "price": 0.55, "timestamp": 1700000000}
    out = _parse_tick(msg)
    assert out is not None
    t, price, ev = out
    assert t == 1700000000
    assert price == 0.55
    assert ev == "last_trade_price"


def test_parse_tick_best_bid_ask():
    msg = {
        "event_type": "best_bid_ask",
        "best_bid": 0.5,
        "best_ask": 0.6,
    }
    out = _parse_tick(msg)
    assert out is not None
    _, price, ev = out
    assert abs(price - 0.55) < 1e-6
    assert ev == "best_bid_ask"


def test_parse_resolved():
    msg = {"winning_asset_id": "token-yes-1", "winning_outcome": "Yes"}
    aid, out = _parse_resolved(msg)
    assert aid == "token-yes-1"
    assert out == "Yes"


def test_write_tick_to_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = get_connection(path)
        init_db(conn)
        conn.execute(
            "INSERT INTO markets (condition_id, slug, closed) VALUES ('0xc1', 'm1', 0)"
        )
        conn.commit()
        write_tick_to_db(conn, "0xc1", 1700000000, 0.55, "last_trade_price")
        cur = conn.execute("SELECT condition_id, t, price, event_type FROM live_ticks")
        row = cur.fetchone()
        assert row == ("0xc1", 1700000000, 0.55, "last_trade_price")
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_write_resolved_to_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = get_connection(path)
        init_db(conn)
        conn.execute(
            "INSERT INTO markets (condition_id, slug, closed, resolution_outcome) "
            "VALUES ('0xc1', 'm1', 1, NULL)"
        )
        conn.commit()
        write_resolved_to_db(conn, "0xc1", "Yes")
        cur = conn.execute("SELECT resolution_outcome FROM markets WHERE condition_id = '0xc1'")
        assert cur.fetchone()[0] == "YES"
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)
