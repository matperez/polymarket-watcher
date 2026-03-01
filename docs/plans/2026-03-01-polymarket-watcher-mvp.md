# polymarket-watcher MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a background service that continuously validates hypotheses (Brier on resolved markets, particle filter backtest, one live PF over WebSocket) using Polymarket APIs, SQLite, in one process with clear ingestion vs engine layers, runnable in Docker on VPS.

**Architecture:** Two layers in one process: Ingestion (Gamma/CLOB/WSS → SQLite raw tables); Engine (read SQLite, run predmkt_sim Brier and PF, write aggregates). Config via env; SQLite in Docker volume; venv, pytest, ruff for dev.

**Tech Stack:** Python 3.10+, httpx (or aiohttp), websockets, sqlite3, predmkt_sim (from local polymarket or pip), pytest, ruff. Docker.

---

## Task 1: Project bootstrap

**Files:**
- Create: `polymarket-watcher/pyproject.toml`
- Create: `polymarket-watcher/README.md`
- Create: `polymarket-watcher/.gitignore`
- Create: `polymarket-watcher/src/polymarket_watcher/__init__.py`

**Step 1: Create pyproject.toml**

- [build-system] setuptools, [project] name polymarket-watcher, version 0.1.0, python >= "3.10", dependencies: httpx, websockets, (predmkt_sim via path or extra). [project.optional-dependencies] dev: pytest, pytest-asyncio, ruff. [tool.ruff] line-length 100, target Python 3.10.

**Step 2: Create README**

- Short description (background watcher for Polymarket hypothesis validation). Instructions: venv (`python -m venv .venv`), activate, `pip install -e ".[dev]"`. Env vars (DATABASE_PATH, LIVE_MARKET_SLUG, intervals). Run: `python -m polymarket_watcher`. Docker: build, run with volume for data. Link to design doc.

**Step 3: Create .gitignore**

- .venv/, __pycache__/, *.db, .env, data/, dist/, *.egg-info/.

**Step 4: Create package init**

- Empty or minimal `__init__.py` under `src/polymarket_watcher/`.

**Step 5: Verify venv and install**

- From repo root: `python -m venv .venv`, `pip install -e ".[dev]"`. If predmkt_sim is path dependency, add `pip install -e /path/to/polymarket` or document in README.

**Step 6: Commit**

- git init (if new repo), git add ., git commit -m "chore: bootstrap polymarket-watcher project"

---

## Task 2: SQLite schema and DB layer

**Files:**
- Create: `polymarket-watcher/src/polymarket_watcher/schema.sql`
- Create: `polymarket_watcher/src/polymarket_watcher/db.py`
- Create: `polymarket-watcher/tests/test_db.py`

**Step 1: Write schema.sql**

- CREATE TABLE for markets, price_snapshots, price_series, live_ticks, predictions, brier_aggregates, particle_filter_runs, pf_live_estimates with columns per design doc. Use INTEGER PRIMARY KEY, REAL for prices, INTEGER for ts where appropriate.

**Step 2: Write failing test for db.init_db**

- In tests/test_db.py: test that init_db(connection or path) creates tables and that a simple insert/select works (e.g. insert into markets one row, select count).

**Step 3: Run test (expect fail)**

- pytest tests/test_db.py -v → FAIL (no db module or init_db).

**Step 4: Implement db.py**

- get_connection(path) returning sqlite3.Connection; init_db(conn) that executes schema.sql or CREATE TABLE IF NOT EXISTS for each table. Call init_db in get_connection or expose init_db for startup.

**Step 5: Run test (expect pass)**

- pytest tests/test_db.py -v → PASS.

**Step 6: Commit**

- git add schema.sql db.py tests/test_db.py; git commit -m "feat: add SQLite schema and db init"

---

## Task 3: Config from env

**Files:**
- Create: `polymarket-watcher/src/polymarket_watcher/config.py`
- Create: `polymarket-watcher/tests/test_config.py`

**Step 1: Write failing test**

- test that load_config() returns an object with database_path, gamma_base_url, clob_base_url, live_market_slug (optional), intervals (gamma_poll_min, etc.), and that defaults are set when env is empty.

**Step 2: Run test (expect fail)**

- pytest tests/test_config.py -v → FAIL.

**Step 3: Implement config.py**

- Load os.environ; define defaults (GAMMA_BASE_URL=https://gamma-api.polymarket.com, CLOB_BASE_URL=https://clob.polymarket.com, DATABASE_PATH=./data/watcher.db, GAMMA_POLL_INTERVAL_MIN=10, etc.). Return a simple dataclass or namespace.

**Step 4: Run test (expect pass)**

- pytest tests/test_config.py -v → PASS.

**Step 5: Commit**

- git add config.py tests/test_config.py; git commit -m "feat: add config from env"

---

## Task 4: Gamma client and poller (ingestion)

**Files:**
- Create: `polymarket-watcher/src/polymarket_watcher/ingestion/gamma.py`
- Create: `polymarket_watcher/tests/test_gamma.py`

**Step 1: Write failing test**

- Mock httpx.get for Gamma /events?closed=true; test that fetch_closed_events(limit=2) returns a list of events with markets, each market has condition_id, token_id_yes (or clobTokenIds), slug, question, endDate, closed. Parse from real-shaped JSON fixture or mock response.

**Step 2: Run test (expect fail)**

- pytest tests/test_gamma.py -v → FAIL.

**Step 3: Implement gamma.py**

- fetch_closed_events(base_url, limit, offset) using httpx.get; parse JSON; normalize to list of events with markets; extract condition_id, token_ids (from market or outcomePrices/clobTokenIds), slug, question, end_date_ts, closed. Handle pagination if needed. No DB write in this module.

**Step 4: Run test (expect pass)**

- pytest tests/test_gamma.py -v → PASS.

**Step 5: Add Gamma poller that writes to DB**

- In gamma.py or a small poller function: fetch_closed_events, then for each market upsert into markets table (INSERT OR REPLACE or check exists then UPDATE). Use db.get_connection. Test with in-memory SQLite: run poller, assert markets table has rows.

**Step 6: Commit**

- git add ingestion/gamma.py tests/test_gamma.py; git commit -m "feat: add Gamma client and poller"

---

## Task 5: CLOB price fetcher (ingestion)

**Files:**
- Create: `polymarket-watcher/src/polymarket_watcher/ingestion/clob.py`
- Create: `polymarket-watcher/tests/test_clob.py`

**Step 1: Write failing test**

- Mock httpx.get for CLOB /prices-history?market=TOKEN_ID; response with history: [{t: ts, p: 0.55}, ...]. Test that fetch_prices_history(token_id, end_ts) returns list of (t, p); and that price_snapshot_for_brier(history, end_date_ts, hours_before=24) returns single price (e.g. closest to end_date_ts - 24*3600).

**Step 2: Run test (expect fail)**

- pytest tests/test_clob.py -v → FAIL.

**Step 3: Implement clob.py**

- fetch_prices_history(base_url, token_id, end_ts=None, start_ts=None) → list of (t, p). Helper: price_snapshot_for_brier(history, end_date_ts, hours_before=24) → float or None. Then function that for a list of markets (from DB) that are closed and lack a price_snapshot, fetches history and inserts one row into price_snapshots (snapshot_at_ts = end_date_ts - 24*3600, price = from helper).

**Step 4: Run test (expect pass)**

- pytest tests/test_clob.py -v → PASS.

**Step 5: Commit**

- git add ingestion/clob.py tests/test_clob.py; git commit -m "feat: add CLOB price history and snapshot fetcher"

---

## Task 6: WebSocket client and live ticks (ingestion)

**Files:**
- Create: `polymarket_watcher/src/polymarket_watcher/ingestion/wss.py`
- Create: `polymarket-watcher/tests/test_wss.py` (optional, can mock)

**Step 1: Implement wss.py**

- Connect to wss://ws-subscriptions-clob.polymarket.com/ws/market; send subscribe message with assets_ids=[token_id], type=market, custom_feature_enabled=true. On message: if event_type last_trade_price or best_bid_ask, parse price and timestamp; push to a queue (queue.Queue) or callback. On market_resolved, parse winning_asset_id/winning_outcome and expose via callback or queue. Run in a thread so main loop is not blocked. Reconnect on disconnect with backoff.

**Step 2: Add writer to DB**

- When a tick is received, insert into live_ticks (condition_id, t, price, event_type). Either write in same thread or batch from queue in a small writer thread. On market_resolved, UPDATE markets SET resolution_outcome = ... WHERE condition_id = ... (map winning_asset_id to YES/NO if needed).

**Step 3: Optional test**

- Unit test with mock websocket or integration test that connects and receives one message (skip if flaky). Or skip tests for WSS and add later.

**Step 4: Commit**

- git add ingestion/wss.py tests/test_wss.py (if any); git commit -m "feat: add WebSocket client for live ticks and resolution"

---

## Task 7: Brier job (engine)

**Files:**
- Create: `polymarket-watcher/src/polymarket_watcher/engine/brier.py`
- Create: `polymarket-watcher/tests/test_brier_job.py`

**Step 1: Write failing test**

- Prepare in-memory DB: insert 3 markets (closed=1, resolution_outcome YES/NO/YES); insert 3 price_snapshots (same condition_ids, prices 0.6, 0.4, 0.8). Run brier job (compute_brier_aggregate(conn)). Assert brier_aggregates has one row with n_markets=3 and brier_score equal to mean of (pred-outcome)^2 for the three (0.6-1)^2, (0.4-0)^2, (0.8-1)^2 then mean. Use predmkt_sim.brier_score for the calculation in engine.

**Step 2: Run test (expect fail)**

- pytest tests/test_brier_job.py -v → FAIL.

**Step 3: Implement engine/brier.py**

- Query: SELECT m.condition_id, m.resolution_outcome, p.price FROM markets m JOIN price_snapshots p ON m.condition_id = p.condition_id WHERE m.closed = 1 AND m.resolution_outcome IS NOT NULL. Map outcome YES->1, NO->0. Build lists predictions, outcomes. Call brier_score(predictions, outcomes). INSERT into brier_aggregates (period='all', n_markets, brier_score, updated_at). Optionally INSERT into predictions (market_snapshot) per market.

**Step 4: Run test (expect pass)**

- pytest tests/test_brier_job.py -v → PASS.

**Step 5: Commit**

- git add engine/brier.py tests/test_brier_job.py; git commit -m "feat: add Brier job (engine)"

---

## Task 8: Particle filter backtest job (engine)

**Files:**
- Create: `polymarket-watcher/src/polymarket_watcher/engine/pf_backtest.py`
- Create: `polymarket-watcher/tests/test_pf_backtest.py`

**Step 1: Write failing test**

- In-memory DB: one market (closed, resolution_outcome=1); price_series with 10 points (t, p) with p trending up. Run pf_backtest for that condition_id: load series, create PredictionMarketParticleFilter(prior_prob=0.5), for each (t,p) call update(p), then estimate(). Assert particle_filter_runs has one row with run_type=backtest, outcome=1, and final_estimate in [0,1].

**Step 2: Run test (expect fail)**

- pytest tests/test_pf_backtest.py -v → FAIL.

**Step 3: Implement engine/pf_backtest.py**

- Select closed markets that have at least N rows in price_series. For each: load price_series ordered by t; instantiate PredictionMarketParticleFilter; for each (t, p) call update(p); get final estimate; get outcome 0/1 from markets.resolution_outcome; INSERT into particle_filter_runs (condition_id, run_type='backtest', final_estimate, outcome). Use a seed for reproducibility in test.

**Step 4: Run test (expect pass)**

- pytest tests/test_pf_backtest.py -v → PASS.

**Step 5: Commit**

- git add engine/pf_backtest.py tests/test_pf_backtest.py; git commit -m "feat: add particle filter backtest job"

---

## Task 9: Live PF updater (engine)

**Files:**
- Create: `polymarket-watcher/src/polymarket_watcher/engine/live_pf.py`
- Create: `polymarket-watcher/tests/test_live_pf.py` (optional)

**Step 1: Implement live_pf.py**

- Class or module: holds one PredictionMarketParticleFilter instance for the live condition_id. on_tick(price): call pf.update(price); optionally store latest estimate. on_snapshot_interval(): write (condition_id, ts, estimate) to pf_live_estimates. on_market_resolved(outcome): write particle_filter_runs (run_type=live, final_estimate, outcome). The WSS layer (or main loop) will call on_tick when a tick arrives; a timer or separate thread calls on_snapshot_interval; on_market_resolved when WSS sends market_resolved.

**Step 2: Wire to ingestion**

- From wss.py callback or from main loop reading live_ticks: pass price to live_pf.on_tick. When market_resolved is received, call live_pf.on_market_resolved(outcome). Ensure PF state is created once when live market is set (e.g. at startup or when first tick arrives).

**Step 3: Optional test**

- Unit test: create LivePFUpdater(condition_id); feed 5 ticks; assert get_estimate() in [0,1]; call on_snapshot_interval and check DB has row.

**Step 4: Commit**

- git add engine/live_pf.py tests/test_live_pf.py (if any); git commit -m "feat: add live particle filter updater"

---

## Task 10: Main loop and orchestration

**Files:**
- Create: `polymarket-watcher/src/polymarket_watcher/main.py`
- Modify: `polymarket-watcher/src/polymarket_watcher/__main__.py` (or main.py as entry)

**Step 1: Implement main.py**

- Load config; init_db(conn); start WebSocket thread with live token_id (from config), passing tick callback to live_pf and resolution callback. Main loop (or asyncio): every GAMMA_POLL_INTERVAL_MIN run Gamma poller (write markets); every CLOB_POLL_INTERVAL_MIN run CLOB fetcher (write price_snapshots); every BRIER_JOB_INTERVAL_MIN run Brier job; every PF_BACKTEST_INTERVAL_MIN run PF backtest job. For live PF snapshot, use a timer (e.g. every 2 min) or run inside the WSS thread. Catch exceptions, log, continue. Sleep between iterations to avoid busy loop.

**Step 2: __main__.py**

- if __name__ == "__main__": from polymarket_watcher.main import run; run().

**Step 3: Manual smoke test**

- Set DATABASE_PATH=./data/test.db, LIVE_MARKET_SLUG= (or leave empty to skip WSS). Run python -m polymarket_watcher for 1–2 minutes; check no crash; check DB has tables and possibly rows if API returned data.

**Step 4: Commit**

- git add main.py __main__.py; git commit -m "feat: add main loop and orchestration"

---

## Task 11: Dockerfile and README update

**Files:**
- Create: `polymarket-watcher/Dockerfile`
- Modify: `polymarket-watcher/README.md`
- Create: `polymarket-watcher/docker-compose.yml` (optional)

**Step 1: Dockerfile**

- FROM python:3.10-slim. WORKDIR /app. COPY pyproject.toml, setup.cfg or src layout. Install predmkt_sim: either COPY ../polymarket and pip install -e polymarket or pip install from git. RUN pip install -e . (no dev deps). COPY src/ . or COPY . . ENTRYPOINT ["python", "-m", "polymarket_watcher"]. ENV DATABASE_PATH=/data/watcher.db. VOLUME /data.

**Step 2: README**

- Add section Docker: docker build -t polymarket-watcher .; docker run -v $(pwd)/data:/data -e LIVE_MARKET_SLUG=your-slug polymarket-watcher. Document env vars (DATABASE_PATH, GAMMA_BASE_URL, CLOB_BASE_URL, LIVE_MARKET_SLUG or LIVE_TOKEN_ID, intervals).

**Step 3: Optional docker-compose**

- service watcher: build ., volumes [./data:/data], env_file .env or environment section.

**Step 4: Commit**

- git add Dockerfile README.md docker-compose.yml; git commit -m "feat: add Docker and run instructions"

---

## Task 12: Lint and CI

**Files:**
- Modify: `polymarket-watcher/pyproject.toml` (ruff config)
- Create: `polymarket-watcher/.github/workflows/ci.yml` (optional)

**Step 1: Run ruff**

- ruff check src/ tests/; fix any issues. Add ruff format if desired.

**Step 2: Add CI workflow (optional)**

- On push: install deps, ruff check, pytest. Skip if no GitHub.

**Step 3: Commit**

- git add .; git commit -m "chore: add lint and CI"

---

## Execution handoff

Plan saved to `docs/plans/2026-03-01-polymarket-watcher-mvp.md`.

**Two options:**

1. **Subagent-driven (this session)** — Run tasks one by one with a subagent per task; you review between tasks.
2. **Parallel session** — Open a new session, use **superpowers:executing-plans** to execute the plan with checkpoints.

Which do you prefer?
