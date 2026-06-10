"""Tests for the AR(1)-on-residuals forecaster."""
from __future__ import annotations

import os

import numpy as np

from battery import load_prices
from battery.forecast import weekday_hour_average
from battery.ar1_forecast import weekday_hour_ar1

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "caseB_grid_battery_market_hourly.csv")


def _p_da():
    _, p_da = load_prices(DATA)
    return p_da.astype(float)


def test_leakage_future_corruption_does_not_change_early_forecast():
    p_da = _p_da()
    for h in (96, 100, 168, 240):
        clean = weekday_hour_ar1(p_da, h, horizon=24)
        bad = p_da.copy()
        bad[h:] = -1e6
        poisoned = weekday_hour_ar1(bad, h, horizon=24)
        assert np.allclose(clean, poisoned), f"leakage at h={h}"


def test_early_fallback_matches_weekday_average():
    p_da = _p_da()
    for h in (48, 60, 71):
        a = weekday_hour_ar1(p_da, h, horizon=24)
        b = weekday_hour_average(p_da, h, horizon=24)
        assert np.allclose(a, b), f"fallback mismatch at h={h}"


def test_phi_zero_reduces_to_weekday_average():
    p_da = _p_da()
    for h in (96, 200, 500):
        a = weekday_hour_ar1(p_da, h, horizon=24, phi=0.0)
        b = weekday_hour_average(p_da, h, horizon=24)
        assert np.allclose(a, b), f"phi=0 mismatch at h={h}"


def test_only_past_is_read():
    # NaN out the future; a leakage-free forecaster still returns finite values
    p_da = _p_da()
    h = 200
    bad = p_da.copy()
    bad[h:] = np.nan
    fc = weekday_hour_ar1(bad, h, horizon=24)
    assert np.all(np.isfinite(fc))
