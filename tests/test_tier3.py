"""Tier 3 tests: the arbitrage LP must honour the frequency response reserve."""
import os

from battery import BatteryParams, load_prices, solve_arbitrage

DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "data", "caseB_grid_battery_market_hourly.csv")
DUR_H = 0.5                       # sustain duration the energy floor is sized for


def _prices():
    _, p_da = load_prices(DATA)
    return p_da[:240]            # 10 days, enough to exercise the reserve quickly


def test_zero_reserve_matches_unconstrained():
    """Zero reserve must leave the optimiser exactly as it was (no behaviour change)."""
    par, p = BatteryParams(), _prices()
    base = solve_arbitrage(p, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh)["profit_gbp"]
    same = solve_arbitrage(p, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
                           reserve_power_kw=0.0, reserve_energy_kwh=0.0)["profit_gbp"]
    assert abs(base - same) < 1e-6


def test_reserve_leaves_power_and_energy_headroom():
    """With a reserve set, every hour must keep the reserved discharge power free and
    enough stored energy to sustain it for its duration."""
    par, p = BatteryParams(), _prices()
    r_kw = 400.0
    e_floor = r_kw * DUR_H / par.eta_dis
    out = solve_arbitrage(p, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
                          reserve_power_kw=r_kw, reserve_energy_kwh=e_floor)
    net = out["discharge_kw"] - out["charge_kw"]
    assert net.max() <= par.p_max_kw - r_kw + 1e-6       # always r_kw of upward headroom
    assert out["soc_kwh"].min() >= e_floor - 1e-6        # always enough energy to sustain it


def test_reserve_reduces_profit():
    """Reserving capacity can only cost arbitrage profit, never raise it."""
    par, p = BatteryParams(), _prices()
    base = solve_arbitrage(p, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh)["profit_gbp"]
    res = solve_arbitrage(p, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
                          reserve_power_kw=500.0,
                          reserve_energy_kwh=500.0 * DUR_H / par.eta_dis)["profit_gbp"]
    assert res < base
