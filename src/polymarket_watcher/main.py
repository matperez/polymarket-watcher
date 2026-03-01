"""Main loop: config, DB init, Gamma/CLOB pollers, Brier/PF jobs, optional WebSocket + live PF."""

import logging
import threading
import time
from pathlib import Path

from polymarket_watcher.config import load_config
from polymarket_watcher.db import get_connection, init_db
from polymarket_watcher.engine.brier import compute_brier_aggregate
from polymarket_watcher.engine.live_pf import LivePFUpdater
from polymarket_watcher.engine.pf_backtest import run_pf_backtest
from polymarket_watcher.ingestion.clob import poll_clob_snapshots_to_db
from polymarket_watcher.ingestion.gamma import poll_gamma_to_db
from polymarket_watcher.ingestion.wss import (
    run_ws_in_thread,
    write_resolved_to_db,
    write_tick_to_db,
)

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL_SEC = 120  # live PF snapshot every 2 min


def run() -> None:
    cfg = load_config()
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    Path(cfg.database_path).parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(cfg.database_path)
    init_db(conn)
    db_lock = threading.Lock()

    live_pf: LivePFUpdater | None = None
    if cfg.live_token_id and cfg.live_condition_id:
        live_pf = LivePFUpdater(cfg.live_condition_id)

        def on_tick(condition_id: str, t: int, price: float, event_type: str) -> None:
            with db_lock:
                write_tick_to_db(conn, condition_id, t, price, event_type)
            if live_pf and condition_id == cfg.live_condition_id:
                live_pf.on_tick(price)

        def on_resolved(condition_id: str, outcome: str | None) -> None:
            with db_lock:
                write_resolved_to_db(conn, condition_id, outcome)
            if live_pf and condition_id == cfg.live_condition_id:
                live_pf.on_market_resolved(conn, outcome)

        run_ws_in_thread(
            asset_ids=[cfg.live_token_id],
            token_to_condition_id={cfg.live_token_id: cfg.live_condition_id},
            on_tick=on_tick,
            on_resolved=on_resolved,
        )
        logger.info("WebSocket and live PF started for condition_id=%s", cfg.live_condition_id)

    last_gamma = 0.0
    last_clob = 0.0
    last_brier = 0.0
    last_pf_backtest = 0.0
    last_pf_snapshot = 0.0
    interval_sec = 60  # check every minute

    try:
        while True:
            now = time.time()

            if now - last_gamma >= cfg.gamma_poll_interval_min * 60:
                try:
                    with db_lock:
                        n = poll_gamma_to_db(conn, cfg.gamma_base_url, limit=100)
                    logger.info("Gamma poll: %d markets", n)
                    last_gamma = now
                except Exception as e:
                    logger.exception("Gamma poll failed: %s", e)

            if now - last_clob >= cfg.clob_poll_interval_min * 60:
                try:
                    with db_lock:
                        n = poll_clob_snapshots_to_db(conn, cfg.clob_base_url)
                    logger.info("CLOB snapshots: %d", n)
                    last_clob = now
                except Exception as e:
                    logger.exception("CLOB poll failed: %s", e)

            if now - last_brier >= cfg.brier_job_interval_min * 60:
                try:
                    with db_lock:
                        score = compute_brier_aggregate(conn)
                    if score is not None:
                        logger.info("Brier aggregate: score=%.4f", score)
                    last_brier = now
                except Exception as e:
                    logger.exception("Brier job failed: %s", e)

            if now - last_pf_backtest >= cfg.pf_backtest_interval_min * 60:
                try:
                    with db_lock:
                        n = run_pf_backtest(conn)
                    if n > 0:
                        logger.info("PF backtest: %d runs", n)
                    last_pf_backtest = now
                except Exception as e:
                    logger.exception("PF backtest failed: %s", e)

            if live_pf and now - last_pf_snapshot >= SNAPSHOT_INTERVAL_SEC:
                try:
                    with db_lock:
                        live_pf.on_snapshot_interval(conn)
                    last_pf_snapshot = now
                except Exception as e:
                    logger.exception("Live PF snapshot failed: %s", e)

            time.sleep(interval_sec)
    except KeyboardInterrupt:
        logger.info("Shutting down")
