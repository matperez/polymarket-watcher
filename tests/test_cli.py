"""Tests for CLI (API client)."""

from unittest.mock import patch

from polymarket_watcher.cli import _cmd_list, _get_base_url


def test_get_base_url_default():
    assert _get_base_url(None) == "http://localhost:8080"


def test_get_base_url_from_arg():
    assert _get_base_url("http://127.0.0.1:9090") == "http://127.0.0.1:9090"


def test_get_base_url_strips_trailing_slash():
    assert _get_base_url("http://localhost:8080/") == "http://localhost:8080"


@patch("polymarket_watcher.cli.httpx.get")
def test_cmd_list_calls_api_and_prints_json(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = [
        {"condition_id": "0xa", "token_id_yes": "123"},
    ]
    exit_code = _cmd_list("http://test")
    assert exit_code == 0
    mock_get.assert_called_once_with("http://test/watched", timeout=30.0)
