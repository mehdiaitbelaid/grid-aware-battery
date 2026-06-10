from __future__ import annotations

import numpy as np

from .forecast import weekday_hour_average


def _fixed_effects(past):
    """Global mean, 24 hour-of-day effects, 7 day-of-week effects, fit on `past`.
    Fitted value at index t is g + he[t % 24] + de[(t // 24) % 7]."""
    h = len(past)
    idx = np.arange(h)
    hod = idx % 24
    dow = (idx // 24) % 7
    g = float(past.mean())
    he = np.array([past[hod == k].mean() - g if (hod == k).any() else 0.0 for k in range(24)])
    de = np.array([past[dow == k].mean() - g if (dow == k).any() else 0.0 for k in range(7)])
    return g, he, de


def weekday_hour_ar1(series, h: int, horizon: int = 24, phi=None):
    """weekday_hour_average plus an AR(1) carry on its residuals.

    Fit the fixed effects on series[:h], take the residual at the same hour 24h back, and add
    phi times it. phi is the lag-1 autocorrelation of the past residuals, clipped to [0, 0.95].
    Falls back to weekday_hour_average for h < 72 (too few days for a stable phi). Reads only
    series[:h].
    """
    series = np.asarray(series, dtype=float)

    if h < 72:
        return weekday_hour_average(series, h, horizon)

    past = series[:h]
    g, he, de = _fixed_effects(past)

    # Fitted values and residuals on the observed past.
    t_past = np.arange(h)
    fitted_past = g + he[t_past % 24] + de[(t_past // 24) % 7]
    resid = past - fitted_past

    # Estimate phi as the lag-1 autocorrelation of the residual series, unless given.
    if phi is None:
        r0 = resid[:-1]
        r1 = resid[1:]
        denom = float(np.dot(r0, r0))
        phi_hat = float(np.dot(r0, r1) / denom) if denom > 0.0 else 0.0
        phi = float(np.clip(phi_hat, 0.0, 0.95))

    # Forecast: fixed-effect mean plus the AR(1) carry of the most recent same-hour residual.
    fc = np.empty(horizon)
    for k in range(horizon):
        t = h + k
        fitted = g + he[t % 24] + de[(t // 24) % 7]
        lag = t - 24                      # most recent same-hour-of-day residual, always < h here
        fc[k] = fitted + phi * resid[lag]
    return fc
