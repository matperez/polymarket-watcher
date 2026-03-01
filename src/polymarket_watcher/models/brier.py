"""Brier score for calibration (Part II of Quant Desk article)."""

import numpy as np


def brier_score(
    predictions: list[float] | np.ndarray,
    outcomes: list[float] | list[int] | np.ndarray,
) -> float:
    """
    Brier score: mean squared error between predictions and outcomes.

    Brier = (1/n) * sum((p_i - y_i)^2). Lower is better.
    """
    p = np.asarray(predictions, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    return float(np.mean((p - y) ** 2))
