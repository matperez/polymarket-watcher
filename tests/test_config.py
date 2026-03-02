"""Tests for config from env."""

import os

from polymarket_watcher.config import load_config


def test_load_config_returns_object_with_expected_fields_and_defaults():
    # Clear relevant env to test defaults
    for key in [
        "DATABASE_PATH",
        "GAMMA_BASE_URL",
        "CLOB_BASE_URL",
        "API_HOST",
        "API_PORT",
        "GAMMA_POLL_INTERVAL_MIN",
        "CLOB_POLL_INTERVAL_MIN",
        "BRIER_JOB_INTERVAL_MIN",
        "PF_BACKTEST_INTERVAL_MIN",
        "LOG_LEVEL",
    ]:
        os.environ.pop(key, None)
    cfg = load_config()
    assert cfg.database_path == "./data/watcher.db"
    assert cfg.gamma_base_url == "https://gamma-api.polymarket.com"
    assert cfg.clob_base_url == "https://clob.polymarket.com"
    assert cfg.api_host == "0.0.0.0"
    assert cfg.api_port == 8080
    assert cfg.gamma_poll_interval_min == 10
    assert cfg.clob_poll_interval_min == 15
    assert cfg.brier_job_interval_min == 15
    assert cfg.pf_backtest_interval_min == 60
    assert cfg.log_level == "INFO"


def test_load_config_reads_env_overrides():
    os.environ["DATABASE_PATH"] = "/tmp/test.db"
    os.environ["GAMMA_POLL_INTERVAL_MIN"] = "5"
    try:
        cfg = load_config()
        assert cfg.database_path == "/tmp/test.db"
        assert cfg.gamma_poll_interval_min == 5
    finally:
        os.environ.pop("DATABASE_PATH", None)
        os.environ.pop("GAMMA_POLL_INTERVAL_MIN", None)
