"""Tests for the battery arbitrage optimiser."""
import os

from battery import BatteryParams, load_prices, solve_arbitrage

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
