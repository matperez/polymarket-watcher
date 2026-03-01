# polymarket-watcher MVP — Design

**Date:** 2026-03-01  
**Project:** `~/projects/polymarket-watcher` (new repo)  
**Scope:** Background service to continuously validate hypotheses (Brier, particle filter backtest, one live PF over WebSocket). SQLite, Docker, venv, tests, linter.

---

## 1. High-level architecture

- **Single process in Docker**, two logical layers:
  - **Ingestion:** only reads from Polymarket APIs and writes raw data to SQLite. No predmkt_sim, no Brier/PF computation. Tasks: Gamma poll (closed events + market metadata), CLOB poll (prices-history for snapshots, optional price_series), one WebSocket subscription for live contract (ticks + market_resolved). Writes: markets, events (optional), price_snapshots, price_series, live_ticks.
  - **Engine:** reads from SQLite, calls predmkt_sim (Brier, particle filter), writes results to SQLite (predictions, brier_aggregates, particle_filter_runs, pf_live_estimates). Runs on schedule (e.g. every 10–15 min) or on trigger. Live PF: consumes ticks (in-memory queue or DB), updates PF state, persists estimates periodically and on market_resolved.
- **Single SQLite DB** (one file, Docker volume). Ingestion writes; engine reads and writes.
- **Config:** env vars (poll intervals, LIVE_MARKET_SLUG or LIVE_TOKEN_ID, DATABASE_PATH, LOG_LEVEL). No secrets for public APIs.
- **Tooling:** venv in repo root, `pip install -e ".[dev]"` with pytest, ruff (or flake8). Tests and lint in CI and before commit.

---

## 2. Data model (SQLite)

- **markets** — condition_id (PK), token_id_yes, token_id_no, slug, question, end_date_ts, closed (bool), resolution_outcome (YES/NO/null), event_slug (optional), created_at, updated_at.
- **events** — optional; id, slug, title, closed, end_date_ts. Can be skipped in MVP and store event_slug on markets only.
- **price_snapshots** — id, condition_id, snapshot_at_ts, price (real), source (e.g. 'midpoint'|'last_trade'). One row per “Brier snapshot” (e.g. price 24h before end_date).
- **price_series** — id, condition_id, t (unix ts), p (price). Index (condition_id, t).
- **live_ticks** — id, condition_id, t, price, event_type. Filled by WebSocket ingestion.
- **predictions** — id, condition_id, model_type ('market_snapshot'|'particle_filter_final'), predicted_prob, created_at.
- **brier_aggregates** — id, period ('day'|'week'|'all'), period_start_ts (optional), n_markets, brier_score, updated_at.
- **particle_filter_runs** — id, condition_id, run_type ('backtest'|'live'), started_at, final_estimate, outcome (0/1 after resolution), created_at.
- **pf_live_estimates** — id, condition_id, ts, estimate, created_at. Periodic snapshots of live PF.

Migrations: one initial schema (e.g. `schema.sql` or Alembic initial revision); app checks on startup and creates tables if missing.

---

## 3. Components

**Ingestion**

- **Gamma poller** — GET Gamma /events?closed=true (paginated). Upsert markets (condition_id, token_ids, slug, question, end_date_ts, closed). Set resolution_outcome if provided by API or leave null until market_resolved.
- **CLOB price fetcher** — For markets missing a Brier snapshot: GET CLOB prices-history for token_id_yes, take price ~24h before end_date, insert into price_snapshots. Optionally fetch full history for closed markets and insert into price_series.
- **WebSocket client** — Subscribe to CLOB WSS with assets_ids=[live token_id]. On last_trade_price / best_bid_ask write to live_ticks (optionally via in-memory queue + batch writer). On market_resolved update markets.resolution_outcome.

**Engine**

- **Brier job** — Select closed markets with resolution_outcome and join price_snapshots. Compute Brier; aggregate by period; write brier_aggregates and optionally predictions (market_snapshot).
- **PF backtest job** — Select closed markets with price_series. Run PredictionMarketParticleFilter over series; compare final estimate to outcome; write particle_filter_runs (backtest) and optionally predictions.
- **Live PF updater** — Consume live ticks (queue or recent live_ticks). update(price); periodically write estimate to pf_live_estimates; on market_resolved write particle_filter_runs (live).

**Orchestration:** Main loop or asyncio: run Gamma + CLOB on timer; WebSocket in separate thread/task; run Brier and PF backtest on timer; live PF updater in WSS callback or reader from queue/DB. All intervals from env.

**predmkt_sim:** Used only in engine (brier_score, PredictionMarketParticleFilter). In Docker install via pip from local polymarket path or git.

---

## 4. Data flow, scheduling, errors, config, Docker

- **Flow:** Gamma → markets; CLOB → price_snapshots, price_series; WSS → live_ticks, markets.resolution_outcome. Engine: markets + price_snapshots → Brier → brier_aggregates; price_series → PF backtest → particle_filter_runs; live ticks → live PF → pf_live_estimates, on resolve → particle_filter_runs.
- **Defaults (env):** GAMMA_POLL_INTERVAL_MIN=10, CLOB_POLL_INTERVAL_MIN=15, BRIER_JOB_INTERVAL_MIN=15, PF_BACKTEST_INTERVAL_MIN=60, PF_LIVE_SNAPSHOT_INTERVAL_MIN=2.
- **Errors:** Try/except on HTTP and WSS; log and continue. WSS reconnect on disconnect. SQLite retry on lock. Fatal (e.g. DB open fail) → log and exit(1) for restart.
- **Config env:** DATABASE_PATH, GAMMA_BASE_URL, CLOB_BASE_URL, WSS_URL, LIVE_MARKET_SLUG or LIVE_TOKEN_ID, intervals, LOG_LEVEL.
- **Docker:** Single image; Python 3.10+; install deps + predmkt_sim; entrypoint `python -m polymarket_watcher`. Volume for DB (e.g. /data). README with docker build/run examples.
- **venv, tests, linter:** venv at repo root; pytest (unit for Brier from fixtures, PF step; optional integration with mocked httpx); ruff in dev deps; run in CI and locally.

---

## Approval log

- Sec 1 (architecture): approved  
- Sec 2 (data model + venv/tests/lint): approved  
- Sec 3 (components): approved  
- Sec 4 (flow, schedule, errors, config, Docker): approved  
