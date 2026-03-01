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
