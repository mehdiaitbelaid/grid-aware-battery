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
