"""Tests for CLOB price history and snapshot fetcher."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx

from polymarket_watcher.db import get_connection, init_db
from polymarket_watcher.ingestion.clob import (
    fetch_prices_history,
    poll_clob_series_to_db,
    poll_clob_snapshots_to_db,
    price_snapshot_for_brier,
)

_PRICES_HISTORY_RESPONSE = {
    "history": [
        {"t": 1705000000, "p": 0.45},
        {"t": 1705086400, "p": 0.52},
        {"t": 1705172800, "p": 0.55},
        {"t": 1705259200, "p": 0.58},
    ]
}


def test_fetch_prices_history_returns_list_of_t_p():
    resp = httpx.Response(200, json=_PRICES_HISTORY_RESPONSE)
    resp.raise_for_status = lambda: None
    with patch("polymarket_watcher.ingestion.clob.httpx.get", return_value=resp):
        history = fetch_prices_history(
            base_url="https://clob.polymarket.com",
            token_id="token-yes-1",
            end_ts=1705345600,
        )
    assert history == [
        (1705000000, 0.45),
        (1705086400, 0.52),
        (1705172800, 0.55),
        (1705259200, 0.58),
    ]


def test_price_snapshot_for_brier_returns_closest_price():
    history = [(1705000000, 0.45), (1705086400, 0.52), (1705172800, 0.55), (1705259200, 0.58)]
    # end_date_ts - 24h -> closest is 1705172800 with p=0.55
    price = price_snapshot_for_brier(history, end_date_ts=1705259200, hours_before=24)
    assert price is not None
    assert price == 0.55  # closest to target_ts is 1705172800 with p=0.55


def test_price_snapshot_for_brier_empty_history_returns_none():
    assert price_snapshot_for_brier([], end_date_ts=1705259200, hours_before=24) is None


def test_poll_clob_snapshots_to_db_fetches_and_inserts():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = get_connection(path)
        init_db(conn)
        # One market with token_id_yes, end_date_ts; no snapshot yet
        conn.execute(
            """INSERT INTO markets (condition_id, token_id_yes, slug, closed, end_date_ts)
               VALUES ('0xcond1', 'token-yes-1', 'm1', 1, 1705259200)"""
        )
        conn.commit()
        resp = httpx.Response(200, json=_PRICES_HISTORY_RESPONSE)
        resp.raise_for_status = lambda: None
        with patch("polymarket_watcher.ingestion.clob.httpx.get", return_value=resp):
            n = poll_clob_snapshots_to_db(
                conn=conn,
                base_url="https://clob.polymarket.com",
                hours_before=24,
            )
        assert n >= 1
        cur = conn.execute(
            "SELECT condition_id, snapshot_at_ts, price FROM price_snapshots"
        )
        rows = cur.fetchall()
        assert len(rows) >= 1
        assert rows[0][0] == "0xcond1"
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)


def test_poll_clob_series_to_db_inserts_series():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = get_connection(path)
        init_db(conn)
        conn.execute(
            """INSERT INTO markets (condition_id, token_id_yes, slug, closed, end_date_ts)
               VALUES ('0xcond2', 'token-yes-2', 'm2', 1, 1705259200)"""
        )
        conn.commit()
        series = [(1705000000, 0.4), (1705086400, 0.5), (1705172800, 0.55)]
        with patch(
            "polymarket_watcher.ingestion.clob.fetch_prices_history_chunked",
            return_value=series,
        ):
            n = poll_clob_series_to_db(conn, "https://clob.polymarket.com", max_markets_per_run=5)
        assert n == 3
        cur = conn.execute("SELECT condition_id, t, p FROM price_series ORDER BY t")
        rows = cur.fetchall()
        assert len(rows) == 3
        assert rows[0] == ("0xcond2", 1705000000, 0.4)
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)
