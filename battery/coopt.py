from __future__ import annotations

import warnings

import numpy as np
from pulp import (
    LpMaximize, LpProblem, LpStatus, LpVariable, PULP_CBC_CMD, lpSum, value,
)

from .arbitrage import BatteryParams
from .forecast import weekday_hour_average


def solve_coopt(p_da, avail, params: BatteryParams = BatteryParams(),
                e_start: float | None = None, e_end_min: float | None = None,
                block_size: int = 4, terminal_price: float | None = None) -> dict:
    """Co-optimize day-ahead arbitrage and a standby DC reserve over the whole horizon.

    The reserve r is a decision variable, one per block of `block_size` consecutive
    hours, applied to every hour in that block. Arbitrage net dispatch must leave
    r of upward power headroom and the stored energy must always cover the reserve's
    half-hour delivery. The single LP picks how much capacity to sell as reserve and
    how much to trade against the spread, jointly.
    """
    par = params
    p_da = np.asarray(p_da, dtype=float)
    avail = np.asarray(avail, dtype=float)
    T = len(p_da)
    dt = par.dt_h
    e_start = par.e0_kwh if e_start is None else e_start

    n_blocks = (T + block_size - 1) // block_size            # ceil: last block may be short

    m = LpProblem("coopt", LpMaximize)
    pch = [LpVariable(f"c{t}", 0, par.p_max_kw) for t in range(T)]
    pdis = [LpVariable(f"d{t}", 0, par.p_max_kw) for t in range(T)]
    e = [LpVariable(f"E{t}", 0, par.e_cap_kwh) for t in range(T + 1)]
    rblock = [LpVariable(f"r{b}", 0, par.p_max_kw) for b in range(n_blocks)]

    def r_at(t):
        return rblock[t // block_size]

    # Arbitrage at p_da (GBP/MWh, power kW -> /1000) plus DC availability revenue (GBP/MW/h)
    arb = lpSum(p_da[t] * (pdis[t] - pch[t]) * dt / 1000.0 for t in range(T))
    dc = lpSum(avail[t] * (r_at(t) / 1000.0) * dt for t in range(T))
    obj = arb + dc
    if terminal_price is not None:
        obj = obj + terminal_price * e[T] / 1000.0
    m += obj

    m += e[0] == e_start
    for t in range(T):
        m += e[t + 1] == (e[t] + par.eta_ch * pch[t] * dt
                          - pdis[t] / par.eta_dis * dt)
        # power headroom: keep r of upward room above net discharge
        m += pdis[t] - pch[t] <= par.p_max_kw - r_at(t)
        # energy deliverability: hold enough stored energy to sustain r for 0.5 h
        m += e[t] >= r_at(t) * 0.5 / par.eta_dis
    if e_end_min is not None:
        m += e[T] >= e_end_min

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")          # PuLP/CBC emits a noisy solver deprecation warning
        m.solve(PULP_CBC_CMD(msg=0))
    assert LpStatus[m.status] == "Optimal", f"LP not optimal: {LpStatus[m.status]}"

    # CBC returns values with sub-tolerance residuals (order 1e-5) at binding constraints.
    # Snap to 1e-4 kW / kWh so reconstructed dispatch satisfies the headroom and energy floors
    # to the 1e-6 test tolerance without changing any physically meaningful quantity.
    charge = np.round(np.array([value(v) for v in pch]), 4)
    discharge = np.round(np.array([value(v) for v in pdis]), 4)
    soc = np.round(np.array([value(v) for v in e]), 4)
    reserve = np.round(np.array([value(r_at(t)) for t in range(T)]), 4)

    arb_gbp = float(np.sum(p_da * (discharge - charge) * dt / 1000.0))
    dc_gbp = float(np.sum(avail * reserve / 1000.0 * dt))
    total = arb_gbp + dc_gbp
    return {
        "total_gbp": total,
        "arb_gbp": arb_gbp,
        "dc_gbp": dc_gbp,
        "charge_kw": charge,
        "discharge_kw": discharge,
        "soc_kwh": soc,
        "reserve_kw": reserve,
    }


def run_coopt_mpc(p_da, avail, params: BatteryParams = BatteryParams(), horizon: int = 24,
                  da_forecast_fn=weekday_hour_average, av_forecast_fn=weekday_hour_average,
                  block_size: int = 4) -> dict:
    """Rolling MPC over the co-optimized LP.

    Each hour h>=1 forecasts the next `horizon` hours of both p_da and avail (the avail
    forecast is clipped at >=0), solves the same co-opt LP from the current SoC with a
    terminal value equal to the mean of the day-ahead forecast, commits the first hour of
    trade and, on a block boundary, commits the reserve for that block. Reserve blocks are
    aligned to the GLOBAL hour index, so a mid-block re-solve pins r to the committed value.
    Revenue is booked at ACTUAL prices: arbitrage at p_da[h] and standby at avail[h]*r.
    """
    par = params
    p_da = np.asarray(p_da, dtype=float)
    avail = np.asarray(avail, dtype=float)
    T = len(p_da)
    dt = par.dt_h

    e = par.e0_kwh
    charge = np.zeros(T)
    discharge = np.zeros(T)
    soc = np.zeros(T + 1)
    soc[0] = e
    reserve = np.zeros(T)

    committed_r = None        # the reserve currently committed for the active global block

    for h in range(T):
        if h == 0:                                        # no price history yet: no trade, r=0
            soc[h + 1] = e
            reserve[h] = 0.0
            continue

        # new global block starts: clear any pinned reserve so the LP can re-choose it
        if h % block_size == 0:
            committed_r = None

        da_fc = np.asarray(da_forecast_fn(p_da, h, horizon), dtype=float)
        av_fc = np.asarray(av_forecast_fn(avail, h, horizon), dtype=float)
        if da_fc.size == 0:                               # defensive guard at the end of the data
            da_fc = p_da[h:h + 1]
            av_fc = avail[h:h + 1]
        av_fc = np.clip(av_fc, 0.0, None)
        term = float(np.mean(da_fc))

        plan = _solve_coopt_aligned(da_fc, av_fc, par, e_start=e, terminal_price=term,
                                    block_size=block_size, global_h=h,
                                    committed_r=committed_r)

        c0 = float(plan["charge_kw"][0])                  # commit only the first hour of trade
        d0 = float(plan["discharge_kw"][0])
        charge[h] = c0
        discharge[h] = d0

        # at a block boundary, commit the reserve for the whole block from this re-solve
        if committed_r is None:
            committed_r = float(plan["reserve_kw"][0])
        reserve[h] = committed_r

        e = e + par.eta_ch * c0 * dt - d0 / par.eta_dis * dt
        e = min(max(e, 0.0), par.e_cap_kwh)
        soc[h + 1] = e

    arb_gbp = float(np.sum(p_da * (discharge - charge) * dt / 1000.0))
    dc_gbp = float(np.sum(avail * reserve / 1000.0 * dt))
    total = arb_gbp + dc_gbp
    return {
        "total_gbp": total,
        "arb_gbp": arb_gbp,
        "dc_gbp": dc_gbp,
        "reserve_kw": reserve,
        "charge_kw": charge,
        "discharge_kw": discharge,
        "soc_kwh": soc,
    }


def _solve_coopt_aligned(p_da, avail, params: BatteryParams, e_start, terminal_price,
                         block_size, global_h, committed_r) -> dict:
    """Co-opt LP over a rolling horizon whose reserve blocks align to the GLOBAL hour index.

    Hour 0 of the horizon is global hour `global_h`. The reserve block that hour k belongs to
    is keyed by (global_h + k)//block_size, so block boundaries land on global multiples of
    block_size rather than on the horizon's own offset. If `committed_r` is set we are mid-block,
    so the block containing horizon hour 0 is pinned to that value.
    """
    par = params
    p_da = np.asarray(p_da, dtype=float)
    avail = np.asarray(avail, dtype=float)
    T = len(p_da)
    dt = par.dt_h

    # global block index of each horizon hour; remap to a dense 0..K-1 for variable creation
    block_keys = [(global_h + k) // block_size for k in range(T)]
    uniq = sorted(set(block_keys))
    key_to_idx = {key: i for i, key in enumerate(uniq)}

    m = LpProblem("coopt_roll", LpMaximize)
    pch = [LpVariable(f"c{t}", 0, par.p_max_kw) for t in range(T)]
    pdis = [LpVariable(f"d{t}", 0, par.p_max_kw) for t in range(T)]
    e = [LpVariable(f"E{t}", 0, par.e_cap_kwh) for t in range(T + 1)]
    rblock = [LpVariable(f"r{i}", 0, par.p_max_kw) for i in range(len(uniq))]

    def r_at(t):
        return rblock[key_to_idx[block_keys[t]]]

    arb = lpSum(p_da[t] * (pdis[t] - pch[t]) * dt / 1000.0 for t in range(T))
    dc = lpSum(avail[t] * (r_at(t) / 1000.0) * dt for t in range(T))
    obj = arb + dc
    if terminal_price is not None:
        obj = obj + terminal_price * e[T] / 1000.0
    m += obj

    m += e[0] == e_start
    for t in range(T):
        m += e[t + 1] == (e[t] + par.eta_ch * pch[t] * dt
                          - pdis[t] / par.eta_dis * dt)
        m += pdis[t] - pch[t] <= par.p_max_kw - r_at(t)
        m += e[t] >= r_at(t) * 0.5 / par.eta_dis

    # mid-block re-solve: pin the reserve of the active block (the one containing horizon hour 0)
    if committed_r is not None:
        m += rblock[key_to_idx[block_keys[0]]] == committed_r

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m.solve(PULP_CBC_CMD(msg=0))
    assert LpStatus[m.status] == "Optimal", f"LP not optimal: {LpStatus[m.status]}"

    return {
        "charge_kw": np.array([value(v) for v in pch]),
        "discharge_kw": np.array([value(v) for v in pdis]),
        "soc_kwh": np.array([value(v) for v in e]),
        "reserve_kw": np.array([value(r_at(t)) for t in range(T)]),
    }
