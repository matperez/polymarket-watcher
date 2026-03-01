# Build from repo root: docker build -t polymarket-watcher .
FROM python:3.10-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e .

ENV DATABASE_PATH=/data/watcher.db
VOLUME /data

ENTRYPOINT ["python", "-m", "polymarket_watcher"]
