from __future__ import annotations

import numpy as np

from .forecast import weekday_hour_average


def _fixed_effects(past):
    """Fit the weekday_hour_average fixed effects on a strictly past window.

    Returns the global mean g, the 24 hour-of-day effects, and the 7 day-of-week
    effects. The fitted value for any absolute index t is
        g + he[t % 24] + de[(t // 24) % 7]
    which matches weekday_hour_average exactly.
    """
    h = len(past)
    idx = np.arange(h)
    hod = idx % 24
    dow = (idx // 24) % 7
    g = float(past.mean())
    he = np.array([past[hod == k].mean() - g if (hod == k).any() else 0.0 for k in range(24)])
    de = np.array([past[dow == k].mean() - g if (dow == k).any() else 0.0 for k in range(7)])
    return g, he, de


def weekday_hour_ar1(series, h: int, horizon: int = 24, phi=None):
    """AR(1)-on-residuals forecaster.

    Start from the weekday_hour_average fixed effects (global mean + hour-of-day
    effect + day-of-week effect) fit on series[:h]. Compute the residual series on
    past data (actual minus fitted). Estimate phi as the lag-1 autocorrelation of
    that residual series, clipped to [0, 0.95], unless phi is supplied.

    Forecast for hour h+k (k = 0..horizon-1):
        fitted(h+k) + phi * residual(h+k-24)
    using the most recent same-hour residual at lag 24. Because h+k-24 < h for every
    k in a 24-step horizon, that residual is always observable.

    For h < 72 there are fewer than three full days, too little to estimate a stable
    AR(1) term, so fall back to weekday_hour_average. Strictly leakage-free: only
    series[:h] is read.
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
