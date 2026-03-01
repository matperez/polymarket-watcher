"""
Particle filter for real-time probability (Part IV of Quant Desk article).

State: logit random walk. Observation: market price (Gaussian). Bootstrap filter.
"""

import numpy as np
from scipy.special import expit, logit


class PredictionMarketParticleFilter:
    """
    Particle filter for a stream of observed prices.

    Use update(observed_price) on each new price, then estimate() for filtered probability.
    """

    def __init__(
        self,
        n_particles: int = 5000,
        prior_prob: float = 0.5,
        sigma_proc: float = 0.3,
        sigma_obs: float = 0.05,
    ):
        self.n = n_particles
        self.sigma_proc = sigma_proc
        self.sigma_obs = sigma_obs
        self.particles = np.clip(
            prior_prob + np.random.randn(n_particles) * 0.05, 0.01, 0.99
        )
        self.weights = np.ones(n_particles) / n_particles

    def update(self, observed_price: float) -> None:
        """Propagate (logit random walk), reweight by observation, resample if ESS low."""
        logit_p = logit(self.particles)
        logit_p = logit_p + np.random.randn(self.n) * self.sigma_proc
        self.particles = np.clip(expit(logit_p), 0.01, 0.99)
        log_lik = -0.5 * ((observed_price - self.particles) / self.sigma_obs) ** 2
        self.weights = self.weights * np.exp(log_lik - log_lik.max())
        self.weights = self.weights / self.weights.sum()
        ess = 1.0 / (self.weights**2).sum()
        if ess < self.n / 2:
            idx = np.random.choice(self.n, size=self.n, replace=True, p=self.weights)
            self.particles = self.particles[idx]
            self.weights = np.ones(self.n) / self.n

    def estimate(self) -> float:
        """Current probability estimate (weighted mean of particles)."""
        return float(np.sum(self.weights * self.particles))
