"""PF backtest: run particle filter over price_series for closed markets, write runs."""

import time

from predmkt_sim.particle_filter import PredictionMarketParticleFilter


def _outcome_to_int(resolution_outcome: str | None) -> int | None:
    if resolution_outcome is None:
        return None
    s = (resolution_outcome or "").strip().upper()
    if s == "YES":
        return 1
    if s == "NO":
        return 0
    return None


def run_pf_backtest(
    conn,
    prior_prob: float = 0.5,
    n_particles: int = 2000,
) -> int:
    """Run PF over price_series per closed market; write particle_filter_runs. Return count."""
    cur = conn.execute(
        """SELECT m.condition_id, m.resolution_outcome
           FROM markets m
           WHERE m.closed = 1
             AND (SELECT COUNT(*) FROM price_series ps WHERE ps.condition_id = m.condition_id) >= 2
           ORDER BY m.condition_id"""
    )
    markets = cur.fetchall()
    now_ts = int(time.time())
    n = 0
    for condition_id, resolution_outcome in markets:
        cur2 = conn.execute(
            "SELECT t, p FROM price_series WHERE condition_id = ? ORDER BY t",
            (condition_id,),
        )
        series = cur2.fetchall()
        if len(series) < 2:
            continue
        pf = PredictionMarketParticleFilter(
            N_particles=n_particles,
            prior_prob=prior_prob,
        )
        for t, p in series:
            pf.update(float(p))
        final_estimate = pf.estimate()
        outcome = _outcome_to_int(resolution_outcome)
        if outcome is None:
            outcome = -1  # unknown
        conn.execute(
            """INSERT INTO particle_filter_runs
               (condition_id, run_type, started_at, final_estimate, outcome, created_at)
               VALUES (?, 'backtest', ?, ?, ?, ?)""",
            (condition_id, series[0][0], final_estimate, outcome, now_ts),
        )
        n += 1
    conn.commit()
    return n
