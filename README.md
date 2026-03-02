# polymarket-watcher

Background service that validates hypotheses on Polymarket: Brier score on resolved markets, particle filter backtest on price history, and one live particle filter over WebSocket. Model code (Brier, particle filter from the Quant Desk article) is included in the project.

## Setup

Use a **venv**:

```bash
cd polymarket-watcher
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Auth and market IDs

**Токен доступа не нужен.** Сервис только читает данные (рынки, цены, WebSocket). Публичные API Polymarket (Gamma, CLOB) работают без авторизации.

**Отслеживаемые рынки** добавляются только через CLI/API (таблица `watched_markets`). Чтобы добавить рынок, нужны `condition_id` и `token_id_yes`. Как получить:

1. Узнай **slug** рынка из URL на polymarket.com (например `will-trump-win-2024`).
2. Запроси метаданные через Gamma (без ключа):
   ```bash
   curl -s "https://gamma-api.polymarket.com/markets/slug/ВАШ_SLUG" | jq '{conditionId, clobTokenIds, question}'
   ```
3. В ответе: **conditionId** → `condition_id`, **clobTokenIds[0]** (токен Yes) → `token_id_yes` для команды `polymarket-watcher-cli add`.

## Config (env)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `./data/watcher.db` | SQLite file path |
| `GAMMA_BASE_URL` | `https://gamma-api.polymarket.com` | Gamma API base |
| `CLOB_BASE_URL` | `https://clob.polymarket.com` | CLOB API base |
| `API_HOST` | `0.0.0.0` | Bind address for HTTP API |
| `API_PORT` | 8080 | Port for HTTP API |
| `GAMMA_POLL_INTERVAL_MIN` | 10 | Minutes between Gamma polls |
| `CLOB_POLL_INTERVAL_MIN` | 15 | Minutes between CLOB price fetches |
| `BRIER_JOB_INTERVAL_MIN` | 15 | Minutes between Brier job runs |
| `PF_BACKTEST_INTERVAL_MIN` | 60 | Minutes between PF backtest runs |
| `LOG_LEVEL` | INFO | Logging level |

## Run

```bash
python -m polymarket_watcher
```

The process starts the **HTTP API** on `API_HOST:API_PORT` (default `0.0.0.0:8080`) and the main loop (Gamma/CLOB poll, Brier, PF backtest, WebSocket + live PF when markets are watched).

## API

Endpoints (same process as the watcher):

| Method | Path | Description |
|--------|------|-------------|
| GET | `/watched` | List all watched markets |
| POST | `/watched` | Add market (body: `condition_id`, `token_id_yes`, optional `slug`) |
| DELETE | `/watched/{condition_id}` | Remove from watch list |
| PUT | `/watched/{condition_id}` | Update (body: optional `slug`) |
| GET | `/watched/{condition_id}/summary` | Summary: last_estimate, ticks_count, resolved |

After POST/DELETE/PUT the watcher reloads the WebSocket subscription list on the next loop iteration.

## CLI

The CLI talks to the running watcher API (install with `pip install -e .` so the script is on PATH):

```bash
# Base URL: env WATCHER_API_URL or --api (default http://localhost:8080)
polymarket-watcher-cli list
polymarket-watcher-cli add 0xabc 12345 --slug my-market
polymarket-watcher-cli remove 0xabc
polymarket-watcher-cli update 0xabc --slug new-slug
polymarket-watcher-cli summary 0xabc
```

Example with custom API URL:

```bash
WATCHER_API_URL=http://127.0.0.1:8080 polymarket-watcher-cli list
# or
polymarket-watcher-cli --api http://127.0.0.1:8080 list
```

Watched markets are stored in the same SQLite DB; only rows in `watched_markets` drive live WebSocket + PF.

## Docker

Build from **repo root** (no external deps):

```bash
cd polymarket-watcher
docker build -t polymarket-watcher .
docker run -v $(pwd)/data:/data -p 8080:8080 -e DATABASE_PATH=/data/watcher.db polymarket-watcher
```

Add watched markets from the host with the CLI: `polymarket-watcher-cli --api http://localhost:8080 add <condition_id> <token_id_yes> [--slug name]`. Data is stored in the mounted volume at `/data/watcher.db`.

## Tests and lint

```bash
pytest tests/ -v
ruff check src/ tests/
```

## Design

- [MVP design](docs/plans/2026-03-01-polymarket-watcher-mvp-design.md)
- [Multi-watch, API, CLI design](docs/plans/2026-03-01-multi-watch-api-cli-design.md)
