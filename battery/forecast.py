"""
Price forecasts for the rolling-horizon MPC.

Each takes (p_da, h, horizon) and returns forecast prices for hours h .. h+horizon-1.
The realistic ones use only past data (no future leakage). `perfect_window` is a sanity
ceiling that uses the true future, to separate the MPC machinery (limited horizon) from
forecast error.
"""
from __future__ import annotations

import numpy as np


def same_hour_average(p_da, h: int, horizon: int = 24, lookback_days: int = 7):
    """Average of each hour-of-day over the last `lookback_days` complete days."""
    current_day = h // 24
    # fallback uses ONLY strictly-past prices; at h=0 there is no history, so a flat
    # forecast (no trade) is used rather than touching the current/future price.
    observed_mean = float(np.mean(p_da[:h])) if h > 0 else 0.0
    fc = np.empty(horizon)
    for k in range(horizon):
        hod = (h + k) % 24
        idx = [d * 24 + hod for d in range(max(0, current_day - lookback_days), current_day)]
        hist = [p_da[i] for i in idx if i < len(p_da)]
        fc[k] = float(np.mean(hist)) if hist else observed_mean
    return fc


def persistence(p_da, h: int, horizon: int = 24):
    """Yesterday's actual prices: 'today looks like yesterday'. Preserves the daily spread."""
    fc = np.empty(horizon)
    # fallback uses ONLY strictly-past prices; flat (no trade) at h=0
    fallback = float(np.mean(p_da[:h])) if h > 0 else 0.0
    for k in range(horizon):
        j = h + k - 24
        fc[k] = float(p_da[j]) if j >= 0 else fallback
    return fc


def perfect_window(p_da, h: int, horizon: int = 24):
    """The true future prices in the window: a ceiling that isolates the limited horizon
    from forecast error (not a real forecast)."""
    return np.asarray(p_da[h:h + horizon], dtype=float)


def perfect_plus_noise(p_da, h: int, horizon: int = 24, sigma: float = 0.0, seed: int = 0):
    """SYNTHETIC forecast-quality probe, NOT a realizable forecast.

    True future prices plus zero-mean Gaussian noise whose standard deviation grows with
    lead time (sqrt of hours ahead, like a random walk). Used only to map profit against
    forecast error for the bonus; it deliberately uses future prices, so a real operator
    could never make this forecast. sigma = 0 recovers perfect foresight.
    """
    true = np.asarray(p_da[h:h + horizon], dtype=float)
    k = np.arange(len(true))
    rng = np.random.default_rng(seed * 1_000_003 + h)   # reproducible per (seed, hour)
    sd = sigma * np.sqrt(1.0 + k)                        # forecast error grows with lead time
    return true + rng.normal(0.0, sd)
