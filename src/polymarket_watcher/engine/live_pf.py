"""Live PF: one PF per condition_id; on_tick, on_snapshot_interval, on_market_resolved."""

import time

from polymarket_watcher.models import PredictionMarketParticleFilter


def _outcome_to_int(outcome: str | int | None) -> int:
    if outcome is None:
        return -1
    if isinstance(outcome, int):
        return 1 if outcome else 0
    s = (str(outcome) or "").strip().upper()
    if s == "YES" or s == "1":
        return 1
    if s == "NO" or s == "0":
        return 0
    return -1


class LivePFUpdater:
    """Holds one particle filter for a live market; writes snapshots and final run to DB."""

    def __init__(
        self,
        condition_id: str,
        prior_prob: float = 0.5,
        n_particles: int = 2000,
    ):
        self.condition_id = condition_id
        self._pf = PredictionMarketParticleFilter(
            n_particles=n_particles,
            prior_prob=prior_prob,
        )
        self._started_at: int | None = None

    def on_tick(self, price: float) -> None:
        """Update filter with new observed price."""
        self._pf.update(price)
        if self._started_at is None:
            self._started_at = int(time.time())

    def get_estimate(self) -> float:
        """Current filtered probability estimate in [0, 1]."""
        return self._pf.estimate()

    def on_snapshot_interval(self, conn) -> None:
        """Write current estimate to pf_live_estimates."""
        est = self.get_estimate()
        ts = int(time.time())
        conn.execute(
            """INSERT INTO pf_live_estimates (condition_id, ts, estimate, created_at)
               VALUES (?, ?, ?, ?)""",
            (self.condition_id, ts, est, ts),
        )
        conn.commit()

    def on_market_resolved(self, conn, outcome: str | int | None) -> None:
        """Write particle_filter_runs row (run_type=live) and optionally clear state."""
        now_ts = int(time.time())
        final_estimate = self.get_estimate()
        outcome_int = _outcome_to_int(outcome)
        conn.execute(
            """INSERT INTO particle_filter_runs
               (condition_id, run_type, started_at, final_estimate, outcome, created_at)
               VALUES (?, 'live', ?, ?, ?, ?)""",
            (
                self.condition_id,
                self._started_at or now_ts,
                final_estimate,
                outcome_int,
                now_ts,
            ),
        )
        conn.commit()
