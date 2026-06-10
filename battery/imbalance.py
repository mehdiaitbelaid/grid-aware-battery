"""Imbalance settlement: a perfect-hindsight ceiling and a first attempt at capturing it.

bestof_bound settles each discharge at the higher of the two prices and each charge at the
lower, with full hindsight. It is an upper bound, not a strategy (you can't know at dispatch
which venue will pay more), so it only says how much spread is on the table.

run_twoprice_mpc is the achievable version: dispatch on the day-ahead forecast, then pick a
settlement venue each hour from a persistence forecast of the imbalance price. Only data known
before the hour is used.
"""

from __future__ import annotations

import warnings

import numpy as np
from pulp import (
    LpMaximize, LpProblem, LpStatus, LpVariable, PULP_CBC_CMD, lpSum, value,
)

from .arbitrage import BatteryParams
from .forecast import weekday_hour_average
from .mpc import run_mpc


def bestof_bound(p_da, imb, params: BatteryParams = BatteryParams(),
                 e_start: float | None = None, e_end_min: float | None = None) -> float:
    """Upper bound: each hour settles discharge at max(da, imb) and charge at min(da, imb) with
    full hindsight, so no real policy can beat it. e_start and e_end_min default to e0, so the
    battery ends as full as it started. Returns GBP.
    """
    par = params
    T = len(p_da)
    p_da = np.asarray(p_da, dtype=float)
    imb = np.asarray(imb, dtype=float)
    assert len(imb) == T, "p_da and imb must be the same length"

    e_start = par.e0_kwh if e_start is None else e_start
    e_end_min = par.e0_kwh if e_end_min is None else e_end_min

    hi = np.maximum(p_da, imb)   # discharge settles at the better (higher) venue
    lo = np.minimum(p_da, imb)   # charge settles at the cheaper (lower) venue

    m = LpProblem("bestof_bound", LpMaximize)
    pch = [LpVariable(f"c{t}", 0, par.p_max_kw) for t in range(T)]
    pdis = [LpVariable(f"d{t}", 0, par.p_max_kw) for t in range(T)]
    e = [LpVariable(f"E{t}", 0, par.e_cap_kwh) for t in range(T + 1)]

    # Price is GBP/MWh, power is kW, hence /1000 to land in GBP.
    m += lpSum((hi[t] * pdis[t] - lo[t] * pch[t]) * par.dt_h / 1000.0 for t in range(T))

    m += e[0] == e_start
    for t in range(T):
        m += e[t + 1] == (e[t] + par.eta_ch * pch[t] * par.dt_h
                          - pdis[t] / par.eta_dis * par.dt_h)
    m += e[T] >= e_end_min

    # prices are positive here, so co-activation never pays; guard with a binary in case a
    # venue price could go negative.
    if float(np.min(lo)) < 0.0:
        on = [LpVariable(f"on{t}", cat="Binary") for t in range(T)]
        for t in range(T):
            m += pch[t] <= par.p_max_kw * on[t]
            m += pdis[t] <= par.p_max_kw * (1 - on[t])

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m.solve(PULP_CBC_CMD(msg=0))
    assert LpStatus[m.status] == "Optimal", f"LP not optimal: {LpStatus[m.status]}"

    obj_val = value(m.objective)
    return float(obj_val) if obj_val is not None else 0.0


def run_twoprice_mpc(p_da, imb, params: BatteryParams = BatteryParams(),
                     horizon: int = 24) -> dict:
    """Achievable two-price capture, not a bound.

    Dispatch is the day-ahead realistic MPC (weekday_hour_average, first hour committed each
    step). For each hour we pick a venue from leakage-free forecasts: persistence of the imbalance
    price (imb[h-24]) against the day-ahead forecast. A discharge routes to imbalance only when it
    is forecast to pay more, a charge only when forecast to cost less; we then settle at the actual
    price and book the cash.
    """
    par = params
    T = len(p_da)
    p_da = np.asarray(p_da, dtype=float)
    imb = np.asarray(imb, dtype=float)
    assert len(imb) == T, "p_da and imb must be the same length"

    # dispatch is the day-ahead realistic MPC
    run = run_mpc(p_da, par, horizon=horizon, forecast_fn=weekday_hour_average)
    charge = run["charge_kw"]
    discharge = run["discharge_kw"]

    use_imb = np.zeros(T, dtype=bool)
    realized = 0.0
    for h in range(T):
        net_kw = discharge[h] - charge[h]      # >0 net discharge (we sell), <0 net charge (we buy)
        if net_kw == 0.0:
            continue

        # leakage-free forecasts for hour h: imbalance persistence and the day-ahead forecast
        imb_fc = float(imb[h - 24]) if h - 24 >= 0 else float(np.mean(imb[:h])) if h > 0 else 0.0
        da_fc_vec = weekday_hour_average(p_da, h, horizon=horizon)
        da_fc = float(da_fc_vec[0])

        if net_kw > 0.0:
            choose_imb = imb_fc > da_fc        # selling: imbalance only if forecast higher
        else:
            choose_imb = imb_fc < da_fc        # buying: imbalance only if forecast lower
        use_imb[h] = choose_imb

        price = float(imb[h]) if choose_imb else float(p_da[h])
        realized += price * net_kw * par.dt_h / 1000.0

    return {
        "charge_kw": charge,
        "discharge_kw": discharge,
        "soc_kwh": run["soc_kwh"],
        "use_imbalance": use_imb,
        "profit_gbp": float(realized),
    }
