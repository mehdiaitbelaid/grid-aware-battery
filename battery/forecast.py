from __future__ import annotations

import numpy as np


def same_hour_average(p_da, h: int, horizon: int = 24, lookback_days: int = 7):
    current_day = h // 24
    # Strictly past data only; at h=0 there is no history, so use a flat no-trade forecast
    observed_mean = float(np.mean(p_da[:h])) if h > 0 else 0.0
    fc = np.empty(horizon)
    for k in range(horizon):
        hod = (h + k) % 24
        idx = [d * 24 + hod for d in range(max(0, current_day - lookback_days), current_day)]
        hist = [p_da[i] for i in idx if i < len(p_da)]
        fc[k] = float(np.mean(hist)) if hist else observed_mean
    return fc


def same_hour_of_week_average(p_da, h: int, horizon: int = 24, lookback_weeks: int = 4):
    # Day-of-week plus hour-of-day baseline: average the same hour-of-week over prior weeks, so
    # weekday and weekend shapes are kept apart. Strictly past data only (the nearest reference is
    # a full week back), so it is leakage-free like same_hour_average.
    observed_mean = float(np.mean(p_da[:h])) if h > 0 else 0.0
    fc = np.empty(horizon)
    for k in range(horizon):
        target = h + k
        idx = [target - 168 * w for w in range(1, lookback_weeks + 1)]
        hist = [p_da[i] for i in idx if 0 <= i < h]          # only weeks that are fully in the past
        fc[k] = float(np.mean(hist)) if hist else observed_mean
    return fc


def weekday_hour_average(p_da, h: int, horizon: int = 24):
    # Additive hour-of-day plus day-of-week effects, fit on strictly past data. Each effect uses
    # every past sample, not sparse weekly buckets, so it is the efficient way to use weekly
    # structure. Leakage-free: only p_da[:h] is read.
    if h < 48:
        return same_hour_average(p_da, h, horizon)   # too few weeks for a weekday effect; use the hour-of-day mean
    past = p_da[:h]
    idx = np.arange(h)
    hod = idx % 24
    dow = (idx // 24) % 7
    g = float(past.mean())
    he = np.array([past[hod == k].mean() - g if (hod == k).any() else 0.0 for k in range(24)])
    de = np.array([past[dow == k].mean() - g if (dow == k).any() else 0.0 for k in range(7)])
    return np.array([g + he[(h + k) % 24] + de[((h + k) // 24) % 7] for k in range(horizon)])


def persistence(p_da, h: int, horizon: int = 24):
    fc = np.empty(horizon)
    # Strictly past data only; flat no-trade fallback at h=0
    fallback = float(np.mean(p_da[:h])) if h > 0 else 0.0
    for k in range(horizon):
        j = h + k - 24
        fc[k] = float(p_da[j]) if j >= 0 else fallback
    return fc


def perfect_window(p_da, h: int, horizon: int = 24):
    return np.asarray(p_da[h:h + horizon], dtype=float)


def perfect_plus_noise(p_da, h: int, horizon: int = 24, sigma: float = 0.0, seed: int = 0):
    true = np.asarray(p_da[h:h + horizon], dtype=float)
    k = np.arange(len(true))
    rng = np.random.default_rng(seed * 1_000_003 + h)   # reproducible per (seed, hour)
    sd = sigma * np.sqrt(1.0 + k)                       # larger error further into the lookahead
    return true + rng.normal(0.0, sd)
