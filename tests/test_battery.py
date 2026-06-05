import os

import numpy as np

from battery import (BatteryParams, load_prices, perfect_window, persistence, run_mpc,
                     same_hour_average, same_hour_of_week_average, weekday_hour_average,
                     solve_arbitrage)

DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "data", "caseB_grid_battery_market_hourly.csv")


def test_perfect_foresight_reproduces_egs_result_and_is_valid():
    _, p_da = load_prices(DATA)
    par = BatteryParams()
    res = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh)

    assert abs(res["profit_gbp"] - 16176.0) < 50.0          # matches the coursework
    soc = res["soc_kwh"]
    assert soc.min() >= -1e-6 and soc.max() <= par.e_cap_kwh + 1e-6
    assert abs(soc[0] - par.e0_kwh) < 1e-6                  # starts where told
    assert soc[-1] >= par.e0_kwh - 1e-6                     # ends at least as full


def test_window_solve_respects_start_soc():
    _, p_da = load_prices(DATA)
    res = solve_arbitrage(p_da[:24], BatteryParams(), e_start=500.0)
    assert abs(res["soc_kwh"][0] - 500.0) < 1e-6
    assert res["profit_gbp"] >= -1e-6


def test_realistic_forecasts_have_no_future_leakage():
    _, p = load_prices(DATA)
    for forecast in (same_hour_average, same_hour_of_week_average, weekday_hour_average, persistence):
        for h in (0, 1, 30, 200, 1000, len(p) - 24, len(p) - 2, len(p) - 1):
            f_clean = forecast(p, h)
            p_corrupt = p.copy()
            p_corrupt[h:] = -1.0e6                 # destroy the present and future
            f_corrupt = forecast(p_corrupt, h)
            assert np.allclose(f_clean, f_corrupt), f"{forecast.__name__} leaks future at h={h}"


def test_causal_mpc_cannot_beat_the_clairvoyant_optimum():
    _, p = load_prices(DATA)
    p = p[:120]
    par = BatteryParams()
    ceiling = solve_arbitrage(p, par, e_start=par.e0_kwh)["profit_gbp"]   # no end rule means clairvoyant
    mpc = run_mpc(p, par, forecast_fn=perfect_window)["profit_gbp"]
    assert mpc <= ceiling + 1.0


def test_degradation_cost_reduces_throughput_and_is_neutral_at_zero():
    _, p_da = load_prices(DATA)
    par = BatteryParams()
    base = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh)
    zero = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
                           degradation_cost_per_mwh=0.0)
    assert abs(zero["profit_gbp"] - base["profit_gbp"]) < 1e-6        # zero cost changes nothing

    priced = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
                             degradation_cost_per_mwh=10.0)
    assert priced["profit_gbp"] <= base["profit_gbp"] + 1e-6          # wear cannot raise net profit
    assert priced["discharge_kw"].sum() <= base["discharge_kw"].sum() + 1e-6   # nor increase cycling


def test_round_trip_efficiency_applied_once():
    # charge cheap (hour 0), discharge dear (hour 1), return to start SoC. What comes back out is
    # the round-trip efficiency times what went in, and the cash is grid-side, eta counted once.
    par = BatteryParams()
    prices = np.array([10.0, 100.0])
    out = solve_arbitrage(prices, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh)
    c, d = out["charge_kw"], out["discharge_kw"]
    assert abs(d[1] - par.eta_ch * par.eta_dis * c[0]) < 1e-3
    expected = (prices[1] * d[1] - prices[0] * c[0]) * par.dt_h / 1000.0
    assert abs(out["profit_gbp"] - expected) < 1e-3
