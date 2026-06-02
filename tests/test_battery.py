"""Tests for the battery arbitrage optimiser."""
import os

import numpy as np

from battery import (BatteryParams, load_prices, perfect_window, persistence,
                     run_mpc, same_hour_average, solve_arbitrage)

DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "data", "caseB_grid_battery_market_hourly.csv")


def test_perfect_foresight_reproduces_egs_result_and_is_valid():
    """One LP over all prices must reproduce the EGS LP Base result and obey the rules."""
    _, p_da = load_prices(DATA)
    par = BatteryParams()
    res = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh)

    assert abs(res["profit_gbp"] - 16176.0) < 50.0          # matches the coursework
    soc = res["soc_kwh"]
    assert soc.min() >= -1e-6 and soc.max() <= par.e_cap_kwh + 1e-6
    assert abs(soc[0] - par.e0_kwh) < 1e-6                  # starts where told
    assert soc[-1] >= par.e0_kwh - 1e-6                     # ends at least as full


def test_window_solve_respects_start_soc():
    """A short window from a custom start SoC must honour it, with non-negative profit."""
    _, p_da = load_prices(DATA)
    res = solve_arbitrage(p_da[:24], BatteryParams(), e_start=500.0)
    assert abs(res["soc_kwh"][0] - 500.0) < 1e-6
    assert res["profit_gbp"] >= -1e-6


def test_realistic_forecasts_have_no_future_leakage():
    """A forecast made at hour h must depend only on prices strictly before h.
    Corrupt every price from h onward; the forecast must be unchanged."""
    _, p = load_prices(DATA)
    for forecast in (same_hour_average, persistence):
        for h in (0, 1, 30, 200, 1000):
            f_clean = forecast(p, h)
            p_corrupt = p.copy()
            p_corrupt[h:] = -1.0e6                 # destroy the present and the future
            f_corrupt = forecast(p_corrupt, h)
            assert np.allclose(f_clean, f_corrupt), f"{forecast.__name__} leaks future at h={h}"


def test_causal_mpc_cannot_beat_the_clairvoyant_optimum():
    """A rolling MPC, even with perfect within-window prices, cannot earn more than the
    full-horizon clairvoyant LP. Checked on a short slice for speed."""
    _, p = load_prices(DATA)
    p = p[:120]
    par = BatteryParams()
    ceiling = solve_arbitrage(p, par, e_start=par.e0_kwh)["profit_gbp"]   # no end rule = clairvoyant
    mpc = run_mpc(p, par, forecast_fn=perfect_window)["profit_gbp"]
    assert mpc <= ceiling + 1.0
