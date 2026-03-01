# Multi-watch, API, CLI — Design

**Date:** 2026-03-01  
**Project:** polymarket-watcher  
**Scope:** Track multiple markets at once; HTTP API to manage watch list and get per-market summary; CLI (separate from watcher process) to drive it.

---

## 1. Goals

- **Multiple deals:** Watcher follows many markets simultaneously (WebSocket + Live PF per market).
- **API:** Get/list, add, remove, update watched markets; get detailed summary for one market.
- **CLI:** Manage watch list and query data via API, without touching the DB or the running watcher process directly.

---

## 2. Storage: table `watched_markets`

- **Columns:** `id` (INTEGER PK AUTOINCREMENT), `condition_id` (TEXT UNIQUE NOT NULL), `token_id_yes` (TEXT NOT NULL), `slug` (TEXT NULL), `created_at` (INTEGER unix ts).
- Single source of truth for "which markets to live-track". Watcher and API both use this table; env `LIVE_*` no longer drives the list (can be ignored when table exists or deprecated later).

---

## 3. API (same process as watcher)

- **Framework:** FastAPI (or Starlette); run in same process as main loop (e.g. in a thread or async task), on a dedicated port (e.g. `API_PORT=8080`, default 8080).
- **Endpoints:**
  - **GET /watched** — List all rows from `watched_markets` (id, condition_id, token_id_yes, slug, created_at).
  - **POST /watched** — Body: `condition_id`, `token_id_yes`, optional `slug`. Insert into `watched_markets`; on success set `watch_list_changed = True`.
  - **DELETE /watched/{condition_id}** — Delete row; set `watch_list_changed = True`.
  - **PUT /watched/{condition_id}** — Update (e.g. slug only); set `watch_list_changed = True`.
  - **GET /watched/{condition_id}/summary** — Detailed summary for one market: latest row from `pf_live_estimates`, count of `live_ticks`, `markets.resolution_outcome` if present; optionally last N ticks or last N PF estimates (N cap e.g. 10).
- **Signal:** Shared in-memory flag `watch_list_changed`. After any mutation (POST/DELETE/PUT) set it to True. Watcher main loop checks at start of each iteration and reloads WSS + PF state when True.

---

## 4. Watcher reload on signal

- At start of each main-loop iteration: if `watch_list_changed` then:
  - Read from DB all rows of `watched_markets`.
  - Build `asset_ids = [token_id_yes, ...]` and `token_to_condition_id = {token_id_yes: condition_id, ...}`.
  - Stop current WSS thread/connection (if any).
  - Start new WSS with `run_ws_in_thread(asset_ids=..., token_to_condition_id=...)`.
  - Build/update `dict[condition_id, LivePFUpdater]`: create updater for new condition_ids, drop for removed ones; keep existing for unchanged.
  - Set `watch_list_changed = False`.
- Callbacks on_tick / on_resolved: resolve condition_id from token; update corresponding LivePFUpdater and DB (ticks, resolution, pf_live_estimates, particle_filter_runs as today). Snapshot every 2 min: iterate over all LivePFUpdater and write to `pf_live_estimates`.

---

## 5. CLI (separate from watcher process)

- **Entrypoint:** e.g. `polymarket-watcher-cli` or `python -m polymarket_watcher.cli`.
- **Subcommands:** `list`, `add`, `remove`, `update`, `summary`. All perform HTTP requests to the API (base URL from env e.g. `WATCHER_API_URL` or flag `--api http://localhost:8080`).
- **Examples:**
  - `polymarket-watcher-cli list`
  - `polymarket-watcher-cli add 0xabc 12345 --slug iran-regime`
  - `polymarket-watcher-cli remove 0xabc`
  - `polymarket-watcher-cli update 0xabc --slug new-slug`
  - `polymarket-watcher-cli summary 0xabc`
- CLI does not open the DB; it only talks to the running watcher’s API.

---

## 6. Backward compatibility

- If `watched_markets` is empty and env `LIVE_TOKEN_ID` / `LIVE_CONDITION_ID` are set, watcher can treat that as "legacy single watch" and subscribe to that one market (optional; can be dropped to keep implementation simple).
- Otherwise: only `watched_markets` drives live subscriptions.

---

## 7. Error handling and testing

- API: validate condition_id/token_id format; 409 on duplicate condition_id for POST; 404 on missing condition_id for DELETE/PUT/GET summary.
- Watcher: if reload fails (e.g. DB read error), log and leave `watch_list_changed` True so next iteration retries.
- Tests: unit tests for API endpoints (with in-memory or test DB); CLI tests that mock HTTP or hit test server; watcher integration test that adds a row, signals, and asserts WSS sees the new subscription (or at least reload runs).

---

## 8. Files to add/change (summary)

- **Schema:** `schema.sql` — add `watched_markets` table; run `init_db` so it exists.
- **API:** New module e.g. `src/polymarket_watcher/api.py` (FastAPI app, routes, DB access, set `watch_list_changed`). Main process starts API server in a thread (e.g. uvicorn) and runs main loop in main thread.
- **State:** Shared object or module-level `watch_list_changed` and optionally current list of condition_ids/updaters accessible from both API and main loop.
- **Main:** In `main.py`, read initial watch list from `watched_markets` (or env fallback); start WSS and PF dict; in loop, check flag and reload; start API server before loop.
- **CLI:** New entrypoint `src/polymarket_watcher/cli.py` (or `cli/` package) with argparse/typer, subcommands calling httpx to API base URL.
- **Config:** Add `API_PORT` (default 8080) and optionally `API_HOST` (default 0.0.0.0 or 127.0.0.1).
