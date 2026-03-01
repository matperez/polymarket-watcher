"""Configuration from environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Runtime config loaded from env with defaults."""

    database_path: str
    gamma_base_url: str
    clob_base_url: str
    api_host: str
    api_port: int
    live_market_slug: str | None
    live_token_id: str | None
    live_condition_id: str | None
    gamma_poll_interval_min: int
    clob_poll_interval_min: int
    brier_job_interval_min: int
    pf_backtest_interval_min: int
    log_level: str


def _int_env(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_config() -> Config:
    """Load config from os.environ with defaults."""
    return Config(
        database_path=os.environ.get("DATABASE_PATH", "./data/watcher.db"),
        gamma_base_url=os.environ.get(
            "GAMMA_BASE_URL", "https://gamma-api.polymarket.com"
        ),
        clob_base_url=os.environ.get("CLOB_BASE_URL", "https://clob.polymarket.com"),
        api_host=os.environ.get("API_HOST", "0.0.0.0"),
        api_port=_int_env("API_PORT", 8080),
        live_market_slug=os.environ.get("LIVE_MARKET_SLUG") or None,
        live_token_id=os.environ.get("LIVE_TOKEN_ID") or None,
        live_condition_id=os.environ.get("LIVE_CONDITION_ID") or None,
        gamma_poll_interval_min=_int_env("GAMMA_POLL_INTERVAL_MIN", 10),
        clob_poll_interval_min=_int_env("CLOB_POLL_INTERVAL_MIN", 15),
        brier_job_interval_min=_int_env("BRIER_JOB_INTERVAL_MIN", 15),
        pf_backtest_interval_min=_int_env("PF_BACKTEST_INTERVAL_MIN", 60),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
