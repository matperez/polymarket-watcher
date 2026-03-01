"""Tests for Gamma API client and poller."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from polymarket_watcher.db import get_connection, init_db
from polymarket_watcher.ingestion.gamma import fetch_closed_events, poll_gamma_to_db

_GAMMA_EVENTS_RESPONSE = [
    {
        "id": "ev1",
        "slug": "event-one",
        "title": "Event One",
        "closed": True,
        "endDate": "2025-01-15T00:00:00.000Z",
        "markets": [
            {
                "conditionId": "0xcond1",
                "question": "Will X happen?",
                "slug": "will-x-happen",
                "endDate": "2025-01-15T00:00:00.000Z",
                "closed": True,
                "clobTokenIds": ["token-yes-1", "token-no-1"],
                "outcomePrices": ["0.6", "0.4"],
            }
        ],
    },
    {
        "id": "ev2",
        "slug": "event-two",
        "closed": True,
        "markets": [
            {
                "conditionId": "0xcond2",
                "question": "Will Y happen?",
                "slug": "will-y-happen",
                "endDate": "2025-02-01T00:00:00.000Z",
                "closed": True,
                "clobTokenIds": ["token-yes-2", "token-no-2"],
            }
        ],
    },
]


@pytest.mark.asyncio
async def test_fetch_closed_events_returns_events_with_markets():
    resp = httpx.Response(200, json=_GAMMA_EVENTS_RESPONSE)
    resp.raise_for_status = lambda: None
    with patch("polymarket_watcher.ingestion.gamma.httpx.AsyncClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        events = await fetch_closed_events(
            base_url="https://gamma-api.polymarket.com", limit=2, offset=0
        )
    assert len(events) == 2
    assert events[0]["slug"] == "event-one"
    markets0 = events[0]["markets"]
    assert len(markets0) == 1
    m = markets0[0]
    assert m["condition_id"] == "0xcond1"
    assert m["slug"] == "will-x-happen"
    assert m["question"] == "Will X happen?"
    assert m["closed"] is True
    assert "end_date_ts" in m
    assert m.get("token_id_yes") == "token-yes-1"
    assert m.get("token_id_no") == "token-no-1"


def test_poll_gamma_to_db_upserts_markets():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = get_connection(path)
        init_db(conn)
        resp = httpx.Response(200, json=_GAMMA_EVENTS_RESPONSE)
        resp.raise_for_status = lambda: None
        with patch("polymarket_watcher.ingestion.gamma.httpx.get", return_value=resp):
            poll_gamma_to_db(
                conn=conn,
                base_url="https://gamma-api.polymarket.com",
                limit=2,
            )
        cur = conn.execute("SELECT condition_id, slug, closed FROM markets ORDER BY condition_id")
        rows = cur.fetchall()
        assert len(rows) == 2
        assert rows[0] == ("0xcond1", "will-x-happen", 1)
        assert rows[1] == ("0xcond2", "will-y-happen", 1)
        conn.close()
    finally:
        Path(path).unlink(missing_ok=True)
