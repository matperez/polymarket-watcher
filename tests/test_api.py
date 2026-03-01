"""Tests for HTTP API (watched markets CRUD)."""

import tempfile
from pathlib import Path

import httpx
import pytest

from polymarket_watcher.api import create_app
from polymarket_watcher.db import get_connection, init_db


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def app(db_path):
    conn = get_connection(db_path)
    init_db(conn)
    conn.close()
    return create_app(db_path)


@pytest.fixture
def client(app):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_watched_list_empty_then_post_then_list_then_delete(client, app):
    r = await client.get("/watched")
    assert r.status_code == 200
    assert r.json() == []

    r = await client.post(
        "/watched",
        json={"condition_id": "0xa", "token_id_yes": "123"},
    )
    assert r.status_code == 201

    r = await client.get("/watched")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["condition_id"] == "0xa"
    assert data[0]["token_id_yes"] == "123"

    r = await client.delete("/watched/0xa")
    assert r.status_code == 204

    r = await client.get("/watched")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_watched_summary_returns_last_estimate_ticks_resolved(client, app, db_path):
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO watched_markets (condition_id, token_id_yes, slug, created_at)"
        " VALUES (?, ?, ?, ?)",
        ("0xcond", "token_yes", "my-slug", 1700000000),
    )
    conn.execute(
        "INSERT INTO markets (condition_id, slug, closed, resolution_outcome)"
        " VALUES (?, ?, ?, ?)",
        ("0xcond", "my-slug", 0, "Yes"),
    )
    conn.execute(
        "INSERT INTO pf_live_estimates (condition_id, ts, estimate, created_at)"
        " VALUES (?, ?, ?, ?)",
        ("0xcond", 1700000100, 0.65, 1700000100),
    )
    conn.execute(
        "INSERT INTO live_ticks (condition_id, t, price, event_type)"
        " VALUES (?, ?, ?, ?)",
        ("0xcond", 1700000001, 0.5, "last_trade_price"),
    )
    conn.execute(
        "INSERT INTO live_ticks (condition_id, t, price, event_type)"
        " VALUES (?, ?, ?, ?)",
        ("0xcond", 1700000002, 0.52, "last_trade_price"),
    )
    conn.commit()
    conn.close()

    r = await client.get("/watched/0xcond/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["last_estimate"] == 0.65
    assert data["ticks_count"] == 2
    assert data["resolved"] == "Yes"


@pytest.mark.asyncio
async def test_watched_summary_404_when_not_watched(db_path):
    conn = get_connection(db_path)
    init_db(conn)
    conn.close()
    app = create_app(db_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/watched/0xunknown/summary")
    assert r.status_code == 404
