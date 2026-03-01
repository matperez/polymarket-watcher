# Build from parent dir that contains polymarket and polymarket-watcher:
#   cd ~/projects && docker build -f polymarket-watcher/Dockerfile -t polymarket-watcher .
FROM python:3.10-slim

WORKDIR /app

# Install predmkt_sim from sibling polymarket (required for Brier and PF engine)
COPY polymarket /tmp/polymarket
RUN pip install --no-cache-dir -e /tmp/polymarket

# Install polymarket-watcher
COPY polymarket-watcher/pyproject.toml polymarket-watcher/README.md ./
COPY polymarket-watcher/src ./src
RUN pip install --no-cache-dir -e .

ENV DATABASE_PATH=/data/watcher.db
VOLUME /data

ENTRYPOINT ["python", "-m", "polymarket_watcher"]
