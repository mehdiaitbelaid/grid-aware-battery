from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from pulp import (
    LpMaximize, LpProblem, LpStatus, LpVariable, PULP_CBC_CMD, lpSum, value,
)


@dataclass
class BatteryParams:
    e_cap_kwh: float = 2000.0   # energy capacity [kWh]
    p_max_kw: float = 1000.0    # charge/discharge power limit [kW]
    eta_ch: float = 0.9381      # charge efficiency (about 88% round trip)
    eta_dis: float = 0.9381     # discharge efficiency
    e0_kwh: float = 1000.0      # nominal starting state of charge [kWh]
    dt_h: float = 1.0           # timestep [h]


def load_prices(path: str):
    df = pd.read_csv(path, parse_dates=["timestamp"])
    return df, df["day_ahead_price_gbp_per_mwh"].to_numpy()


def solve_arbitrage(prices, params: BatteryParams = BatteryParams(),
                    e_start: float | None = None, e_end_min: float | None = None,
                    terminal_price: float | None = None,
                    reserve_power_kw: float = 0.0, reserve_energy_kwh: float = 0.0):
    par = params
    T = len(prices)
    e_start = par.e0_kwh if e_start is None else e_start

    m = LpProblem("arbitrage", LpMaximize)
    pch = [LpVariable(f"c{t}", 0, par.p_max_kw) for t in range(T)]
    pdis = [LpVariable(f"d{t}", 0, par.p_max_kw) for t in range(T)]
    e = [LpVariable(f"E{t}", 0, par.e_cap_kwh) for t in range(T + 1)]

    # Price is GBP/MWh and power is kW, hence the /1000 conversion to GBP
    obj = lpSum(prices[t] * (pdis[t] - pch[t]) * par.dt_h / 1000.0 for t in range(T))
    if terminal_price is not None:
        obj = obj + terminal_price * e[T] / 1000.0
    m += obj

    m += e[0] == e_start
    for t in range(T):
        m += e[t + 1] == (e[t] + par.eta_ch * pch[t] * par.dt_h
                          - pdis[t] / par.eta_dis * par.dt_h)
    if e_end_min is not None:
        m += e[T] >= e_end_min

    # Tier 3 reserve: keep upward headroom and enough stored energy for a response event
    if reserve_power_kw > 0.0:
        for t in range(T):
            m += pdis[t] - pch[t] <= par.p_max_kw - reserve_power_kw
    if reserve_energy_kwh > 0.0:
        for t in range(1, T + 1):   # floor the planned trajectory, not the already-given start SoC
            m += e[t] >= reserve_energy_kwh

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")          # PuLP/CBC emits a noisy solver deprecation warning
        m.solve(PULP_CBC_CMD(msg=0))
    assert LpStatus[m.status] == "Optimal", f"LP not optimal: {LpStatus[m.status]}"

    obj_val = value(m.objective)
    return {
        "charge_kw": np.array([value(v) for v in pch]),
        "discharge_kw": np.array([value(v) for v in pdis]),
        "soc_kwh": np.array([value(v) for v in e]),
        "profit_gbp": float(obj_val) if obj_val is not None else 0.0,
    }
