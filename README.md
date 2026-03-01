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

## Auth and LIVE_* IDs

**Токен доступа не нужен.** Сервис только читает данные (рынки, цены, WebSocket). Публичные API Polymarket (Gamma, CLOB) работают без авторизации.

**LIVE_TOKEN_ID и LIVE_CONDITION_ID** — публичные идентификаторы контракта, не секреты. Как получить:

1. Узнай **slug** рынка из URL на polymarket.com (например `will-trump-win-2024`).
2. Запроси метаданные через Gamma (без ключа):
   ```bash
   curl -s "https://gamma-api.polymarket.com/markets/slug/ВАШ_SLUG" | jq '{conditionId, clobTokenIds, question}'
   ```
3. В ответе: **conditionId** → `LIVE_CONDITION_ID`, **clobTokenIds[0]** (токен Yes) → `LIVE_TOKEN_ID`.

Без `LIVE_*` сервис тоже работает: опрос Gamma/CLOB, Brier и PF backtest по закрытым рынкам; WebSocket и live PF просто не запускаются.

## Config (env)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `./data/watcher.db` | SQLite file path |
| `GAMMA_BASE_URL` | `https://gamma-api.polymarket.com` | Gamma API base |
| `CLOB_BASE_URL` | `https://clob.polymarket.com` | CLOB API base |
| `LIVE_MARKET_SLUG` | — | Slug for live WebSocket (optional) |
| `LIVE_TOKEN_ID` | — | Token ID (Yes) for live market; required with `LIVE_CONDITION_ID` for WSS |
| `LIVE_CONDITION_ID` | — | Condition ID for live market (for DB and live PF) |
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

Build from **repo root** (no external deps):

```bash
cd polymarket-watcher
docker build -t polymarket-watcher .
docker run -v $(pwd)/data:/data -e DATABASE_PATH=/data/watcher.db polymarket-watcher
```

With live WebSocket and PF:

```bash
docker run -v $(pwd)/data:/data \
  -e DATABASE_PATH=/data/watcher.db \
  -e LIVE_TOKEN_ID=<token_id_yes> \
  -e LIVE_CONDITION_ID=<condition_id> \
  polymarket-watcher
```

Data is stored in the mounted volume at `/data/watcher.db`.

## Tests and lint

```bash
pytest tests/ -v
ruff check src/ tests/
```

## Design

See [docs/plans/2026-03-01-polymarket-watcher-mvp-design.md](docs/plans/2026-03-01-polymarket-watcher-mvp-design.md).
