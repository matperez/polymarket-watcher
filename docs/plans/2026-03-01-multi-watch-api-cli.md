# Multi-watch, API, CLI — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add table `watched_markets`, HTTP API (list/add/remove/update watched + summary per market), in-process signal to reload WSS/PF, and CLI that talks to API; watcher supports multiple live markets from DB.

**Architecture:** One process runs main loop + FastAPI on a port; shared `watch_list_changed` flag; on API mutate, set flag; main loop reloads from `watched_markets` and restarts WSS + PF dict. CLI is separate entrypoint, httpx to API.

**Tech Stack:** FastAPI, uvicorn (thread), httpx in CLI, existing SQLite/DB.

---

## Task 1: Schema — table `watched_markets`

**Files:**
- Modify: `src/polymarket_watcher/schema.sql`
- Test: `tests/test_db.py` (extend or add test that table exists and insert/select)

**Step 1:** Add to `schema.sql`:
```sql
CREATE TABLE IF NOT EXISTS watched_markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id TEXT NOT NULL UNIQUE,
    token_id_yes TEXT NOT NULL,
    slug TEXT,
    created_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_watched_markets_condition_id ON watched_markets(condition_id);
```

**Step 2:** Add test in `tests/test_db.py`: after `init_db(conn)`, `conn.execute("INSERT INTO watched_markets (condition_id, token_id_yes, slug, created_at) VALUES (?, ?, ?, ?)", ("0xc1", "tok1", "slug1", 1700000000))`, `conn.commit()`, then `SELECT * FROM watched_markets` and assert one row.

**Step 3:** Run `pytest tests/test_db.py -v`, expect PASS.

**Step 4:** Commit: `git add src/polymarket_watcher/schema.sql tests/test_db.py && git commit -m "feat: add watched_markets table"`

---

## Task 2: API module — FastAPI app, GET/POST/DELETE/PUT /watched, shared flag

**Files:**
- Create: `src/polymarket_watcher/api.py`
- Create: `tests/test_api.py`

**Step 1:** Write failing test: with test client and in-memory DB with `watched_markets`, `GET /watched` returns `[]`; `POST /watched` with body `{"condition_id":"0xa","token_id_yes":"123"}` returns 201; `GET /watched` returns one item; `DELETE /watched/0xa` returns 204; `GET /watched` returns `[]`. Use `httpx.ASGITransport` + FastAPI app, DB path in app state or dependency.

**Step 2:** Run `pytest tests/test_api.py -v`, expect FAIL (no api module).

**Step 3:** Implement `api.py`: FastAPI app, dependency that yields DB path (from app state set at startup); `GET /watched` — select all from watched_markets, return list of dicts; `POST /watched` — parse body, insert, set global `watch_list_changed = True`, return 201; `DELETE /watched/{condition_id}` — delete where condition_id, set flag, return 204; `PUT /watched/{condition_id}` — update slug (or body with slug), set flag, return 200. Module-level variable `watch_list_changed: bool = False` that API sets and main will read.

**Step 4:** Run tests, expect PASS. Commit: `git add src/polymarket_watcher/api.py tests/test_api.py && git commit -m "feat: add API GET/POST/DELETE/PUT /watched and watch_list_changed"`

---

## Task 3: API — GET /watched/{condition_id}/summary

**Files:**
- Modify: `src/polymarket_watcher/api.py`
- Modify: `tests/test_api.py`

**Step 1:** Failing test: insert one row in watched_markets, insert one row in pf_live_estimates and two in live_ticks for that condition_id; `GET /watched/{condition_id}/summary` returns JSON with e.g. `last_estimate`, `ticks_count`, `resolved` (from markets), optionally `last_ticks` or `last_estimates` list. Assert keys and values.

**Step 2:** Run test, expect FAIL.

**Step 3:** Implement endpoint: read from DB — latest pf_live_estimates for condition_id, count of live_ticks, markets.resolution_outcome; return dict. 404 if condition_id not in watched_markets or not found.

**Step 4:** Run tests, PASS. Commit: `git add src/polymarket_watcher/api.py tests/test_api.py && git commit -m "feat: add GET /watched/{condition_id}/summary"`

---

## Task 4: Main — read watch list from DB, start API server in thread, reload on flag

**Files:**
- Modify: `src/polymarket_watcher/main.py`
- Dependency: `api.py` must expose app and `watch_list_changed`; main must be able to pass DB path to API (e.g. app state before starting uvicorn).

**Step 1:** In main: add config for API_PORT (env, default 8080). Before the main loop, start FastAPI with uvicorn in a daemon thread (e.g. `uvicorn.run(app, host="0.0.0.0", port=cfg.api_port)` in thread target); pass database_path into app state so API can open DB. Ensure init_db is called so watched_markets exists.

**Step 2:** Replace single live_token_id/live_condition_id logic with: read from DB `SELECT condition_id, token_id_yes FROM watched_markets`; build asset_ids and token_to_condition_id; if non-empty, start WSS and dict of LivePFUpdater keyed by condition_id. In on_tick/on_resolved, look up condition_id and update the corresponding LivePFUpdater; write ticks/resolved to DB as today. Snapshot: for each LivePFUpdater in dict, call on_snapshot_interval(conn).

**Step 3:** At start of each loop iteration, check `api.watch_list_changed` (or equivalent). If True: re-read watched_markets, stop current WSS (e.g. set a “stop” event or replace the thread), rebuild asset_ids and token_to_condition_id, start new WSS, rebuild dict of LivePFUpdater (create new for new condition_ids, drop for removed), set watch_list_changed = False.

**Step 4:** Manual smoke: run watcher, GET /watched, POST one market, check GET /watched and that watcher log shows WSS reload. Commit: `git add src/polymarket_watcher/main.py && git commit -m "feat: main reads watch list from DB, runs API in thread, reloads WSS on signal"`

---

## Task 5: CLI — list, add, remove, update, summary

**Files:**
- Create: `src/polymarket_watcher/cli.py`
- Create: `tests/test_cli.py` (optional: mock httpx or run against test client)

**Step 1:** CLI entrypoint (argparse or typer): subcommands `list`, `add`, `remove`, `update`, `summary`. Base URL from env `WATCHER_API_URL` or `--api http://localhost:8080`. `list` → GET /watched, print table or JSON. `add` → POST /watched with condition_id, token_id_yes, optional --slug. `remove` → DELETE /watched/{condition_id}. `update` → PUT /watched/{condition_id} with optional --slug. `summary` → GET /watched/{condition_id}/summary, print JSON or formatted.

**Step 2:** Add to pyproject.toml entry point: `[project.scripts] polymarket-watcher-cli = "polymarket_watcher.cli:main"` (or console_scripts).

**Step 3:** Test: run watcher in background, run `polymarket-watcher-cli --api http://127.0.0.1:8080 list`, add, list again, summary, remove. Or unit test with mocked httpx.

**Step 4:** Commit: `git add src/polymarket_watcher/cli.py pyproject.toml tests/test_cli.py && git commit -m "feat: add CLI list/add/remove/update/summary via API"`

---

## Task 6: Config — API_PORT, optional API_HOST; backward compat

**Files:**
- Modify: `src/polymarket_watcher/config.py`
- Modify: `src/polymarket_watcher/main.py` (use cfg.api_port, cfg.api_host)

**Step 1:** Add to Config: api_port (int, default 8080), api_host (str, default "0.0.0.0"). Load from env API_PORT, API_HOST.

**Step 2:** In main, use cfg.api_port and cfg.api_host when starting uvicorn. Update README with API_PORT and WATCHER_API_URL for CLI.

**Step 3:** Commit: `git add src/polymarket_watcher/config.py src/polymarket_watcher/main.py README.md && git commit -m "feat: config API_PORT and API_HOST; README API/CLI usage"`

---

## Task 7: Lint, tests, README

**Files:**
- Modify: `README.md`
- Run: `ruff check src/ tests/`, `pytest tests/ -v`

**Step 1:** Extend README: section "API" (endpoints, port), section "CLI" (install, WATCHER_API_URL, subcommands examples). Fix any ruff issues. Run full test suite.

**Step 2:** Commit: `git add README.md && git commit -m "docs: API and CLI usage in README"`

---

## Execution handoff

Plan saved to `docs/plans/2026-03-01-multi-watch-api-cli.md`.

**Two execution options:**

1. **Subagent-driven (this session)** — Run tasks one by one in this session; review between tasks.
2. **Parallel session (separate)** — Open a new session and use executing-plans to run the plan with checkpoints.

Which approach do you prefer?
