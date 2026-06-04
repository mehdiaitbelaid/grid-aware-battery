"""
Battery arbitrage as a linear program, reusable over any price window.

Ported from the EGS coursework model (a single perfect-foresight LP over all hours)
into a function that solves over an arbitrary horizon from an arbitrary starting state
of charge. The same optimiser then drives both the perfect-foresight baseline (one big
call over all prices) and the rolling-horizon MPC (many small calls over 24 h windows).

Decision variables per hour: charge power, discharge power, and stored energy (SoC).
Objective: maximise arbitrage profit, sum of price * (discharge - charge). Constraints:
fixed start SoC, the lossy energy balance each hour, and an optional minimum end SoC.
"""
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
    """Physical parameters of the 2 MWh / 1 MW battery (kW, kWh, hours)."""

    e_cap_kwh: float = 2000.0   # energy capacity [kWh]
    p_max_kw: float = 1000.0    # charge/discharge power limit [kW]
    eta_ch: float = 0.9381      # charge efficiency (about 88% round trip)
    eta_dis: float = 0.9381     # discharge efficiency
    e0_kwh: float = 1000.0      # nominal starting state of charge [kWh]
    dt_h: float = 1.0           # timestep [h]


def load_prices(path: str):
    """Load the hourly market data. Returns (DataFrame, day-ahead price array GBP/MWh)."""
    df = pd.read_csv(path, parse_dates=["timestamp"])
    return df, df["day_ahead_price_gbp_per_mwh"].to_numpy()


def solve_arbitrage(prices, params: BatteryParams = BatteryParams(),
                    e_start: float | None = None, e_end_min: float | None = None,
                    terminal_price: float | None = None,
                    reserve_power_kw: float = 0.0, reserve_energy_kwh: float = 0.0):
    """Solve the arbitrage LP over one price window.

    prices         : day-ahead prices over the window [GBP/MWh]
    e_start        : starting state of charge [kWh] (defaults to params.e0_kwh)
    e_end_min      : minimum end-of-window state of charge [kWh] (None = unconstrained)
    terminal_price : if given, value leftover end-of-window energy at this price
                     [GBP/MWh], so a finite window does not dump all its charge at the edge
    reserve_power_kw  : keep this much upward (discharge) power free every hour for
                        frequency response, so the schedule never spends the full rating
    reserve_energy_kwh: keep at least this much stored energy every hour, so the reserved
                        power can actually be sustained for its required duration

    Returns a dict: charge_kw, discharge_kw, soc_kwh (length T+1), profit_gbp.
    For the MPC the terminal value is only a planning aid; booked profit uses real prices
    on the committed actions, not this objective.
    """
    par = params
    T = len(prices)
    e_start = par.e0_kwh if e_start is None else e_start

    m = LpProblem("arbitrage", LpMaximize)
    pch = [LpVariable(f"c{t}", 0, par.p_max_kw) for t in range(T)]
    pdis = [LpVariable(f"d{t}", 0, par.p_max_kw) for t in range(T)]
    e = [LpVariable(f"E{t}", 0, par.e_cap_kwh) for t in range(T + 1)]

    # objective: arbitrage profit in GBP (price is GBP/MWh, power in kW, so divide by 1000)
    obj = lpSum(prices[t] * (pdis[t] - pch[t]) * par.dt_h / 1000.0 for t in range(T))
    if terminal_price is not None:
        obj = obj + terminal_price * e[T] / 1000.0   # value energy left at the horizon edge
    m += obj

    m += e[0] == e_start
    for t in range(T):
        m += e[t + 1] == (e[t] + par.eta_ch * pch[t] * par.dt_h
                          - pdis[t] / par.eta_dis * par.dt_h)
    if e_end_min is not None:
        m += e[T] >= e_end_min

    # Tier 3 frequency-response reserve: always keep upward (discharge) headroom and the
    # stored energy to sustain it, so the battery can answer a low-frequency event on demand.
    if reserve_power_kw > 0.0:
        for t in range(T):
            m += pdis[t] - pch[t] <= par.p_max_kw - reserve_power_kw
    if reserve_energy_kwh > 0.0:
        for t in range(T + 1):
            m += e[t] >= reserve_energy_kwh

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")          # hush the PuLP/CBC solver deprecation noise
        m.solve(PULP_CBC_CMD(msg=0))
    assert LpStatus[m.status] == "Optimal", f"LP not optimal: {LpStatus[m.status]}"

    obj_val = value(m.objective)
    return {
        "charge_kw": np.array([value(v) for v in pch]),
        "discharge_kw": np.array([value(v) for v in pdis]),
        "soc_kwh": np.array([value(v) for v in e]),
        "profit_gbp": float(obj_val) if obj_val is not None else 0.0,   # 0 for a flat (no-trade) window
    }
