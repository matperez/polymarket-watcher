# polymarket-watcher

Background service that continuously validates hypotheses on Polymarket: Brier score on resolved markets, particle filter backtest on price history, and one live particle filter over WebSocket. Uses [predmkt_sim](https://github.com/your-org/polymarket) for model code.

## Setup

Use a **venv**:

```bash
cd polymarket-watcher
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Install **predmkt_sim** for engine (Brier, particle filter):

```bash
pip install -e ../polymarket
```

## Config (env)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `./data/watcher.db` | SQLite file path |
| `GAMMA_BASE_URL` | `https://gamma-api.polymarket.com` | Gamma API base |
| `CLOB_BASE_URL` | `https://clob.polymarket.com` | CLOB API base |
| `LIVE_MARKET_SLUG` | — | Slug for live WebSocket (optional) |
| `LIVE_TOKEN_ID` | — | Token ID for live market (alternative to slug) |
| `GAMMA_POLL_INTERVAL_MIN` | 10 | Minutes between Gamma polls |
| `CLOB_POLL_INTERVAL_MIN` | 15 | Minutes between CLOB price fetches |
| `BRIER_JOB_INTERVAL_MIN` | 15 | Minutes between Brier job runs |
| `PF_BACKTEST_INTERVAL_MIN` | 60 | Minutes between PF backtest runs |
| `LOG_LEVEL` | INFO | Logging level |

## Run

```bash
python -m polymarket_watcher
```

## Docker

Build (from repo root; predmkt_sim can be installed from sibling polymarket):

```bash
docker build -t polymarket-watcher .
docker run -v $(pwd)/data:/data -e LIVE_MARKET_SLUG=your-slug polymarket-watcher
```

Data is stored in the mounted volume at `/data/watcher.db` (set `DATABASE_PATH=/data/watcher.db` in container).

## Tests and lint

```bash
pytest tests/ -v
ruff check src/ tests/
```

## Design

See [docs/plans/2026-03-01-polymarket-watcher-mvp-design.md](docs/plans/2026-03-01-polymarket-watcher-mvp-design.md).
