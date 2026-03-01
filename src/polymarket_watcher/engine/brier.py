"""Brier score aggregate job: join markets + price_snapshots, compute Brier, write brier_aggregates."""

import time

from predmkt_sim.monte_carlo import brier_score


def _outcome_to_int(resolution_outcome: str | None) -> int | None:
    if resolution_outcome is None:
        return None
    s = (resolution_outcome or "").strip().upper()
    if s == "YES":
        return 1
    if s == "NO":
        return 0
    return None


def compute_brier_aggregate(conn, period: str = "all") -> float | None:
    """Query closed markets with price_snapshots, compute Brier, insert into brier_aggregates. Returns score or None."""
    cur = conn.execute(
        """SELECT m.condition_id, m.resolution_outcome, ps.price
           FROM markets m
           JOIN price_snapshots ps ON ps.condition_id = m.condition_id
           WHERE m.closed = 1 AND m.resolution_outcome IS NOT NULL
           ORDER BY m.condition_id"""
    )
    rows = cur.fetchall()
    if not rows:
        return None
    predictions = []
    outcomes = []
    for _cid, outcome_str, price in rows:
        o = _outcome_to_int(outcome_str)
        if o is not None and price is not None:
            try:
                predictions.append(float(price))
                outcomes.append(o)
            except (TypeError, ValueError):
                continue
    if not predictions:
        return None
    score = brier_score(predictions, outcomes)
    now_ts = int(time.time())
    conn.execute(
        """INSERT INTO brier_aggregates (period, period_start_ts, n_markets, brier_score, updated_at)
           VALUES (?, NULL, ?, ?, ?)""",
        (period, len(predictions), score, now_ts),
    )
    conn.commit()
    return score
