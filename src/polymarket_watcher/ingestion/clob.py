"""CLOB API client: prices history and Brier snapshot fetcher."""

import logging

import httpx

logger = logging.getLogger(__name__)


def fetch_prices_history(
    base_url: str,
    token_id: str,
    end_ts: int | None = None,
    start_ts: int | None = None,
    interval: str = "all",
) -> list[tuple[int, float]]:
    """Fetch prices-history for token. Returns list of (t, p)."""
    url = f"{base_url.rstrip('/')}/prices-history"
    params: dict = {"market": token_id, "interval": interval}
    if end_ts is not None:
        params["endTs"] = end_ts
    if start_ts is not None:
        params["startTs"] = start_ts
    response = httpx.get(url, params=params, timeout=30.0)
    response.raise_for_status()
    data = response.json()
    history = data.get("history") if isinstance(data, dict) else None
    if not isinstance(history, list):
        return []
    result = []
    for h in history:
        if isinstance(h, dict) and "t" in h and "p" in h:
            try:
                t = int(h["t"])
                p = float(h["p"])
                result.append((t, p))
            except (TypeError, ValueError):
                continue
    return sorted(result, key=lambda x: x[0])


def price_snapshot_for_brier(
    history: list[tuple[int, float]],
    end_date_ts: int,
    hours_before: int = 24,
) -> float | None:
    """Return price from history closest to (end_date_ts - hours_before)."""
    if not history:
        return None
    target = end_date_ts - hours_before * 3600
    best_t, best_p = min(history, key=lambda x: abs(x[0] - target))
    return best_p


# CLOB API rejects "interval too long" when only endTs is set; use a 7-day window
_CLOB_HISTORY_WINDOW_SEC = 7 * 24 * 3600

# Max chunks when fetching full series (e.g. 52 * 7 days ≈ 1 year)
_CLOB_SERIES_MAX_CHUNKS = 52


def fetch_prices_history_chunked(
    base_url: str,
    token_id: str,
    end_ts: int,
    window_sec: int = _CLOB_HISTORY_WINDOW_SEC,
    max_chunks: int = _CLOB_SERIES_MAX_CHUNKS,
) -> list[tuple[int, float]]:
    """
    Fetch full price history by requesting 7-day chunks backward from end_ts.
    Returns sorted list of (t, p). Stops when a chunk is empty or max_chunks reached.
    """
    all_points: list[tuple[int, float]] = []
    seen_t: set[int] = set()
    current_end = end_ts
    for _ in range(max_chunks):
        start_ts = max(0, current_end - window_sec)
        try:
            chunk = fetch_prices_history(
                base_url=base_url,
                token_id=token_id,
                start_ts=start_ts,
                end_ts=current_end,
            )
        except httpx.HTTPStatusError:
            break
        if not chunk:
            break
        for t, p in chunk:
            if t not in seen_t:
                seen_t.add(t)
                all_points.append((t, p))
        if chunk[0][0] <= start_ts:
            break
        current_end = start_ts
        if current_end <= 0:
            break
    return sorted(all_points, key=lambda x: x[0])


def poll_clob_snapshots_to_db(
    conn,
    base_url: str,
    hours_before: int = 24,
) -> int:
    """Fetch history for closed markets missing snapshot, insert one row each. Return count."""
    cur = conn.execute(
        """SELECT m.condition_id, m.token_id_yes, m.end_date_ts
           FROM markets m
           LEFT JOIN price_snapshots ps ON ps.condition_id = m.condition_id
           WHERE m.closed = 1 AND m.token_id_yes IS NOT NULL AND m.end_date_ts IS NOT NULL
             AND ps.id IS NULL"""
    )
    rows = cur.fetchall()
    n = 0
    for condition_id, token_id_yes, end_date_ts in rows:
        if not token_id_yes or not end_date_ts:
            continue
        try:
            start_ts = max(0, end_date_ts - _CLOB_HISTORY_WINDOW_SEC)
            history = fetch_prices_history(
                base_url=base_url,
                token_id=token_id_yes,
                start_ts=start_ts,
                end_ts=end_date_ts,
            )
        except httpx.HTTPStatusError as e:
            logger.debug(
                "CLOB prices-history skip %s: %s", condition_id[:18], e.response.status_code
            )
            continue
        price = price_snapshot_for_brier(history, end_date_ts, hours_before=hours_before)
        if price is None:
            continue
        snapshot_at_ts = end_date_ts - hours_before * 3600
        conn.execute(
            """INSERT INTO price_snapshots (condition_id, snapshot_at_ts, price, source)
               VALUES (?, ?, ?, ?)""",
            (condition_id, snapshot_at_ts, price, "midpoint"),
        )
        n += 1
    conn.commit()
    return n


def poll_clob_series_to_db(
    conn,
    base_url: str,
    max_markets_per_run: int = 5,
) -> int:
    """
    For closed markets with fewer than 2 points in price_series, fetch full history
    in 7-day chunks and insert (condition_id, t, p). Returns total rows inserted.
    """
    cur = conn.execute(
        """SELECT m.condition_id, m.token_id_yes, m.end_date_ts
           FROM markets m
           WHERE m.closed = 1 AND m.token_id_yes IS NOT NULL AND m.end_date_ts IS NOT NULL
             AND (SELECT COUNT(*) FROM price_series ps WHERE ps.condition_id = m.condition_id) < 2
           ORDER BY m.end_date_ts DESC
           LIMIT ?""",
        (max_markets_per_run,),
    )
    rows = cur.fetchall()
    total_inserted = 0
    for condition_id, token_id_yes, end_date_ts in rows:
        if not token_id_yes or not end_date_ts:
            continue
        try:
            history = fetch_prices_history_chunked(
                base_url=base_url,
                token_id=token_id_yes,
                end_ts=end_date_ts,
            )
        except httpx.HTTPStatusError as e:
            logger.debug("CLOB series skip %s: %s", condition_id[:18], e.response.status_code)
            continue
        if len(history) < 2:
            continue
        for t, p in history:
            conn.execute(
                "INSERT OR IGNORE INTO price_series (condition_id, t, p) VALUES (?, ?, ?)",
                (condition_id, t, p),
            )
            total_inserted += 1
    conn.commit()
    return total_inserted
