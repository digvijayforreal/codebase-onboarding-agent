"""Forecast which files are 'heating up' from their monthly commit history.

This is the genuinely different use of time-series here: each file's monthly
commit count is a short series, and we estimate near-future change pressure.
We deliberately use a light, dependency-free approach (recency-weighted mean +
linear trend) rather than a heavy forecasting library -- it is robust on the
very short, spiky series that per-file git history produces.
"""
from __future__ import annotations

import numpy as np


def forecast_pressure(monthly_commits: list[int]) -> float:
    """Return a raw 'heat' value (>=0) predicting near-future churn.

    Combines two signals:
      * recency-weighted average activity (recent months count more)
      * linear trend (is activity accelerating?)
    """
    series = np.asarray(monthly_commits, dtype=float)
    n = series.size
    if n == 0 or series.sum() == 0:
        return 0.0

    # Recency weights: newest month weighted highest.
    weights = np.linspace(1.0, 2.0, n)
    weighted_avg = float(np.average(series, weights=weights))

    # Linear trend via least squares slope over the series.
    x = np.arange(n, dtype=float)
    if n >= 2 and np.ptp(x) > 0:
        slope = float(np.polyfit(x, series, 1)[0])
    else:
        slope = 0.0

    # Project one step ahead: last level nudged by trend, floored at 0.
    projected = max(0.0, weighted_avg + slope)
    # Blend projection with recent level so a single spike does not dominate.
    recent = float(series[-3:].mean()) if n >= 3 else float(series.mean())
    return 0.6 * projected + 0.4 * recent
