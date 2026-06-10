import os

import numpy as np

from battery import BatteryParams, load_prices, solve_arbitrage
from battery.coopt import solve_coopt

DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "data", "caseB_grid_battery_market_hourly.csv")


def _data():
    df, p_da = load_prices(DATA)
    avail = df["ancillary_availability_gbp_per_mw_per_h"].to_numpy()
    return p_da, avail


def test_coopt_efa_beats_fixed_stack():
    # fixed 500 kW is a feasible point of the co-opt LP, so co-opt can't do worse
    par = BatteryParams()
    p_da, avail = _data()
    fixed_arb = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
                                reserve_power_kw=500.0,
                                reserve_energy_kwh=500.0 * 0.5 / par.eta_dis)["profit_gbp"]
    fixed_stack = fixed_arb + 0.5 * float(np.sum(avail))
    coopt = solve_coopt(p_da, avail, par, block_size=4)["total_gbp"]
    assert coopt >= fixed_stack


def test_reserve_genuinely_withheld():
    # net dispatch must leave the booked reserve as headroom; guards against double-counting
    par = BatteryParams()
    p_da, avail = _data()
    out = solve_coopt(p_da, avail, par, block_size=4)
    net = out["discharge_kw"] - out["charge_kw"]
    assert np.all(net <= par.p_max_kw - out["reserve_kw"] + 1e-6)


def test_coopt_efa_beats_pure_arbitrage():
    # DC revenue is non-negative, so co-opt >= pure arbitrage
    par = BatteryParams()
    p_da, avail = _data()
    pure_arb = solve_arbitrage(p_da, par)["profit_gbp"]
    coopt = solve_coopt(p_da, avail, par, block_size=4)["total_gbp"]
    assert coopt >= pure_arb
