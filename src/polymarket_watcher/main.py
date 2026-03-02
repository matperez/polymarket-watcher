"""Main loop: config, DB init, Gamma/CLOB, Brier/PF, API, optional WebSocket + live PF."""

import logging
import threading
import time
from pathlib import Path

import uvicorn

from polymarket_watcher import api as api_module
from polymarket_watcher.config import load_config
from polymarket_watcher.db import get_connection, init_db
from polymarket_watcher.engine.brier import compute_brier_aggregate
from polymarket_watcher.engine.live_pf import LivePFUpdater
from polymarket_watcher.engine.pf_backtest import run_pf_backtest
from polymarket_watcher.ingestion.clob import poll_clob_series_to_db, poll_clob_snapshots_to_db
from polymarket_watcher.ingestion.gamma import poll_gamma_to_db
from polymarket_watcher.ingestion.wss import (
    run_ws_in_thread,
    write_resolved_to_db,
    write_tick_to_db,
)

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL_SEC = 120  # live PF snapshot every 2 min


def _get_watch_list(conn) -> list[tuple[str, str]]:
    """Return [(condition_id, token_id_yes), ...] from watched_markets. Only CLI/API add markets."""
    cur = conn.execute("SELECT condition_id, token_id_yes FROM watched_markets")
    rows = cur.fetchall()
    return [(r[0], r[1]) for r in rows]


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

    app = api_module.create_app(cfg.database_path)
    api_thread = threading.Thread(
        target=lambda: uvicorn.run(
            app,
            host=cfg.api_host,
            port=cfg.api_port,
            log_level="warning",
        ),
        daemon=True,
    )
    api_thread.start()
    logger.info("API listening on %s:%s", cfg.api_host, cfg.api_port)

    # Mutable container so WSS callbacks always see current live PF updaters
    live_pf_container: dict[str, dict[str, LivePFUpdater]] = {"by_cid": {}}
    ws_stop_event: threading.Event | None = None
    ws_thread: threading.Thread | None = None

    def start_wss(watch_list: list[tuple[str, str]]) -> None:
        nonlocal ws_stop_event, ws_thread
        if ws_stop_event:
            ws_stop_event.set()
        if ws_thread:
            ws_thread.join(timeout=5.0)
        if not watch_list:
            ws_stop_event = None
            ws_thread = None
            return
        asset_ids = [t[1] for t in watch_list]
        token_to_condition_id = {t[1]: t[0] for t in watch_list}
        live_pf_container["by_cid"] = {
            cid: LivePFUpdater(cid) for cid, _ in watch_list
        }
        db_path = cfg.database_path

        def on_tick(condition_id: str, t: int, price: float, event_type: str) -> None:
            wss_conn = get_connection(db_path)
            try:
                write_tick_to_db(wss_conn, condition_id, t, price, event_type)
            finally:
                wss_conn.close()
            updater = live_pf_container["by_cid"].get(condition_id)
            if updater:
                updater.on_tick(price)

        def on_resolved(condition_id: str, outcome: str | None) -> None:
            wss_conn = get_connection(db_path)
            try:
                write_resolved_to_db(wss_conn, condition_id, outcome)
                updater = live_pf_container["by_cid"].get(condition_id)
                if updater:
                    updater.on_market_resolved(wss_conn, outcome)
            finally:
                wss_conn.close()

        ws_stop_event = threading.Event()
        ws_thread = run_ws_in_thread(
            asset_ids=asset_ids,
            token_to_condition_id=token_to_condition_id,
            on_tick=on_tick,
            on_resolved=on_resolved,
            stop_event=ws_stop_event,
        )
        logger.info(
            "WebSocket and live PF started for %d markets: %s",
            len(watch_list),
            [t[0] for t in watch_list],
        )

    with db_lock:
        watch_list = _get_watch_list(conn)
    if watch_list:
        start_wss(watch_list)

    last_gamma = 0.0
    last_clob = 0.0
    last_clob_series = 0.0
    last_brier = 0.0
    last_pf_backtest = 0.0
    last_pf_snapshot = 0.0
    interval_sec = 60
    clob_series_interval_min = 60

    try:
        while True:
            now = time.time()

            if api_module.watch_list_changed:
                api_module.watch_list_changed = False
                with db_lock:
                    watch_list = _get_watch_list(conn)
                start_wss(watch_list)

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

            if now - last_clob_series >= clob_series_interval_min * 60:
                try:
                    with db_lock:
                        n = poll_clob_series_to_db(
                            conn, cfg.clob_base_url, max_markets_per_run=5
                        )
                    if n > 0:
                        logger.info("CLOB series: %d points", n)
                    last_clob_series = now
                except Exception as e:
                    logger.exception("CLOB series failed: %s", e)

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

            by_cid = live_pf_container["by_cid"]
            if by_cid and now - last_pf_snapshot >= SNAPSHOT_INTERVAL_SEC:
                try:
                    with db_lock:
                        for updater in by_cid.values():
                            updater.on_snapshot_interval(conn)
                    last_pf_snapshot = now
                except Exception as e:
                    logger.exception("Live PF snapshot failed: %s", e)

            time.sleep(interval_sec)
    except KeyboardInterrupt:
        logger.info("Shutting down")
