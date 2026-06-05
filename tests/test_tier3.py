import os

from battery import BatteryParams, load_prices, solve_arbitrage

DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "data", "caseB_grid_battery_market_hourly.csv")
DUR_H = 0.5                       # sustain duration used to size the energy floor


def _prices():
    _, p_da = load_prices(DATA)
    return p_da[:240]            # 10 days is enough to exercise the reserve quickly


def test_zero_reserve_matches_unconstrained():
    par, p = BatteryParams(), _prices()
    base = solve_arbitrage(p, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh)["profit_gbp"]
    same = solve_arbitrage(p, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
                           reserve_power_kw=0.0, reserve_energy_kwh=0.0)["profit_gbp"]
    assert abs(base - same) < 1e-6


def test_reserve_leaves_power_and_energy_headroom():
    par, p = BatteryParams(), _prices()
    r_kw = 400.0
    e_floor = r_kw * DUR_H / par.eta_dis
    out = solve_arbitrage(p, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
                          reserve_power_kw=r_kw, reserve_energy_kwh=e_floor)
    net = out["discharge_kw"] - out["charge_kw"]
    assert net.max() <= par.p_max_kw - r_kw + 1e-6       # always r_kw of upward headroom
    assert out["soc_kwh"].min() >= e_floor - 1e-6        # always enough energy to sustain it


def test_reserve_reduces_profit():
    par, p = BatteryParams(), _prices()
    base = solve_arbitrage(p, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh)["profit_gbp"]
    res = solve_arbitrage(p, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
                          reserve_power_kw=500.0,
                          reserve_energy_kwh=500.0 * DUR_H / par.eta_dis)["profit_gbp"]
    assert res < base


def test_charge_and_discharge_never_co_activate():
    # net dispatch equals the active converter mode: the LP never charges and discharges at once,
    # so the reserve constraint on net (pdis - pch) is well posed. Round-trip losses make
    # co-activation strictly worse, so the optimum keeps one of the two at zero each hour.
    par, p = BatteryParams(), _prices()
    out = solve_arbitrage(p, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh)
    assert float((out["charge_kw"] * out["discharge_kw"]).max()) < 1e-3
