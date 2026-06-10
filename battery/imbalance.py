"""Imbalance settlement work for the grid-aware battery.

Two pieces live here:

1. ``bestof_bound`` is a perfect-hindsight UPPER bound. It is allowed to settle every
   discharge at whichever of the two prices is higher and every charge at whichever is
   lower, picking the venue with full knowledge of both realized prices. That is not a
   strategy you can run (you cannot know at dispatch time which venue will pay more), so
   the number is a LABELED CEILING used to scale what a real policy captures.

2. ``run_twoprice_mpc`` is the reviewer-honest first step at capturing some of that
   ceiling: a rolling MPC dispatch on a leakage-free day-ahead forecast, with a
   per-hour settlement choice driven by a leakage-free PERSISTENCE forecast of the
   spread. Only quantities knowable at decision time are used, so the realized cash is
   an achievable result rather than a bound.

Terms used here, defined the moment they appear:
  - day-ahead price (``p_da``): the price set a day in advance, GBP per MWh.
  - imbalance price (``imb``): the real-time settlement price for energy that deviates
    from the day-ahead position, GBP per MWh.
  - spread: imbalance price minus day-ahead price for a given hour.
  - settlement venue: which price the hour's net energy is paid at (day-ahead or
    imbalance).
  - leakage-free: a forecast that reads only data from strictly before the hour it
    predicts, so it could have been produced in real time.
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
    """Perfect-hindsight upper bound on imbalance-aware arbitrage value.

    Solves one LP over the whole horizon where each hour's discharge is paid at
    ``max(p_da[t], imb[t])`` and each hour's charge costs ``min(p_da[t], imb[t])``. The
    SoC dynamics, power caps and energy caps are the normal battery model. By construction
    no real policy can beat this: it gets the best of both venues in every direction with
    full foresight. Returns the objective in GBP.

    e_start and e_end_min both default to the nominal start SoC ``e0_kwh``, so the battery
    ends the window with as much energy as it began (no value smuggled in by draining the
    pack).
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

    # Both price vectors are non-negative on this dataset, so simultaneous charge/discharge
    # is never profitable and no binary anti-degeneracy constraint is needed. Guard anyway:
    # if a venue price could go negative, forbid the paid-dump degeneracy with a binary.
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
    """Reviewer-honest two-price dispatch: an achievable capture, not a bound.

    Dispatch: a rolling MPC on the leakage-free ``weekday_hour_average`` day-ahead
    forecast, committing the first hour each step (this is exactly the da-only realistic
    run reused via ``run_mpc``).

    Settlement: for each committed hour ``h`` we choose a venue using only data knowable
    at decision time. The persistence forecast of the imbalance price is ``imb[h-24]``
    (yesterday's same hour); the day-ahead forecast for the hour is the
    ``weekday_hour_average`` forecast value for that hour. If the net dispatch is a
    discharge, imbalance is preferred only when it is forecast to pay MORE than the
    day-ahead forecast; if the net dispatch is a charge, imbalance is preferred only when
    it is forecast to cost LESS. When imbalance is preferred the hour's net energy settles
    at the ACTUAL ``imb[h]``, otherwise at the ACTUAL ``p_da[h]``. We then book the
    realized cash.

    Returns a dict with ``profit_gbp`` (realized cash) plus the dispatch arrays and the
    per-hour venue choice for inspection.
    """
    par = params
    T = len(p_da)
    p_da = np.asarray(p_da, dtype=float)
    imb = np.asarray(imb, dtype=float)
    assert len(imb) == T, "p_da and imb must be the same length"

    # The dispatch itself is the da-only realistic MPC on the weekday-hour-average forecast.
    run = run_mpc(p_da, par, horizon=horizon, forecast_fn=weekday_hour_average)
    charge = run["charge_kw"]
    discharge = run["discharge_kw"]

    use_imb = np.zeros(T, dtype=bool)
    realized = 0.0
    for h in range(T):
        net_kw = discharge[h] - charge[h]      # >0 net discharge (we sell), <0 net charge (we buy)
        if net_kw == 0.0:
            continue

        # Leakage-free forecasts for hour h: persistence of imbalance (yesterday same hour)
        # and the weekday-hour-average day-ahead forecast made at the start of hour h.
        imb_fc = float(imb[h - 24]) if h - 24 >= 0 else float(np.mean(imb[:h])) if h > 0 else 0.0
        da_fc_vec = weekday_hour_average(p_da, h, horizon=horizon)
        da_fc = float(da_fc_vec[0])

        if net_kw > 0.0:
            # Selling: route to imbalance only if it is forecast to pay more.
            choose_imb = imb_fc > da_fc
        else:
            # Buying: route to imbalance only if it is forecast to cost less.
            choose_imb = imb_fc < da_fc
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
