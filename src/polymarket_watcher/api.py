"""HTTP API for managing watched markets and querying summaries."""

import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from polymarket_watcher.db import get_connection, init_db


class AddWatchedBody(BaseModel):
    condition_id: str
    token_id_yes: str
    slug: str | None = None


class UpdateWatchedBody(BaseModel):
    slug: str | None = None

# Set by API on POST/DELETE/PUT; read by main loop to reload WSS/PF.
watch_list_changed: bool = False


def create_app(database_path: str | Path) -> FastAPI:
    """Create FastAPI app with DB path in state."""
    app = FastAPI(title="polymarket-watcher API")
    app.state.database_path = str(database_path)

    @app.get("/watched")
    def list_watched() -> list[dict[str, Any]]:
        conn = get_connection(app.state.database_path)
        try:
            cur = conn.execute(
                "SELECT id, condition_id, token_id_yes, slug, created_at FROM watched_markets"
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "condition_id": r[1],
                    "token_id_yes": r[2],
                    "slug": r[3],
                    "created_at": r[4],
                }
                for r in rows
            ]
        finally:
            conn.close()

    @app.post("/watched", status_code=201)
    def add_watched(body: AddWatchedBody) -> dict[str, str]:
        global watch_list_changed
        condition_id = body.condition_id
        token_id_yes = body.token_id_yes
        slug = body.slug
        conn = get_connection(app.state.database_path)
        try:
            conn.execute(
                "INSERT INTO watched_markets (condition_id, token_id_yes, slug, created_at)"
                " VALUES (?, ?, ?, ?)",
                (condition_id, token_id_yes, slug, int(time.time())),
            )
            conn.commit()
            watch_list_changed = True
            return {"status": "created"}
        finally:
            conn.close()

    @app.delete("/watched/{condition_id}", status_code=204)
    def delete_watched(condition_id: str) -> None:
        global watch_list_changed
        conn = get_connection(app.state.database_path)
        try:
            cur = conn.execute(
                "DELETE FROM watched_markets WHERE condition_id = ?", (condition_id,)
            )
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(404, "not found")
            watch_list_changed = True
        finally:
            conn.close()

    @app.put("/watched/{condition_id}")
    def update_watched(condition_id: str, body: UpdateWatchedBody | None = None) -> dict[str, str]:
        global watch_list_changed
        slug = body.slug if body else None
        conn = get_connection(app.state.database_path)
        try:
            cur = conn.execute(
                "SELECT id FROM watched_markets WHERE condition_id = ?", (condition_id,)
            )
            if cur.fetchone() is None:
                raise HTTPException(404, "not found")
            if slug is not None:
                conn.execute(
                    "UPDATE watched_markets SET slug = ? WHERE condition_id = ?",
                    (slug, condition_id),
                )
                conn.commit()
            watch_list_changed = True
            return {"status": "updated"}
        finally:
            conn.close()

    @app.get("/watched/{condition_id}/summary")
    def get_watched_summary(condition_id: str) -> dict[str, Any]:
        conn = get_connection(app.state.database_path)
        try:
            cur = conn.execute(
                "SELECT 1 FROM watched_markets WHERE condition_id = ?", (condition_id,)
            )
            if cur.fetchone() is None:
                raise HTTPException(404, "not found")
            cur = conn.execute(
                "SELECT resolution_outcome FROM markets WHERE condition_id = ?",
                (condition_id,),
            )
            row = cur.fetchone()
            resolved = row[0] if row else None
            cur = conn.execute(
                "SELECT estimate FROM pf_live_estimates WHERE condition_id = ?"
                " ORDER BY ts DESC LIMIT 1",
                (condition_id,),
            )
            row = cur.fetchone()
            last_estimate = row[0] if row else None
            cur = conn.execute(
                "SELECT COUNT(*) FROM live_ticks WHERE condition_id = ?",
                (condition_id,),
            )
            ticks_count = cur.fetchone()[0]
            return {
                "last_estimate": last_estimate,
                "ticks_count": ticks_count,
                "resolved": resolved,
            }
        finally:
            conn.close()

    return app
