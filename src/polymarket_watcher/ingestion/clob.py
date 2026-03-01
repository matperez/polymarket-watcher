"""CLOB API client: prices history and Brier snapshot fetcher."""

import httpx


def fetch_prices_history(
    base_url: str,
    token_id: str,
    end_ts: int | None = None,
    start_ts: int | None = None,
) -> list[tuple[int, float]]:
    """Fetch prices-history for token. Returns list of (t, p)."""
    url = f"{base_url.rstrip('/')}/prices-history"
    params: dict = {"market": token_id}
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
        history = fetch_prices_history(
            base_url=base_url,
            token_id=token_id_yes,
            end_ts=end_date_ts,
        )
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
