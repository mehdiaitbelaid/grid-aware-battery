"""Risk-aware (CVaR) MPC, used to test the reviewer's overtrading claim.

In the realistic MPC runs, adding a fixed reserve sometimes raises the booked day-ahead profit
instead of lowering it. The reviewer reads that as certainty-equivalent overtrading: a
point-forecast plan makes aggressive first-hour trades that are sometimes wrong, and the reserve
constraint happens to rein them in. If so, a plan that prices forecast uncertainty directly
(CVaR over scenarios) should pick up the same few percent at zero reserve.

Each hour uses only p_da[:h]. Scenarios are the point forecast plus error vectors drawn from the
forecaster's own past errors. The first-hour trade is shared across scenarios; later hours get
per-scenario recourse. The objective is CVaR at level alpha.
"""

from __future__ import annotations

import warnings

import numpy as np
from pulp import (
    LpMaximize, LpProblem, LpStatus, LpVariable, PULP_CBC_CMD, lpSum, value,
)

from .arbitrage import BatteryParams
from .forecast import weekday_hour_average


def _past_step_errors(p_da, h, horizon, base_forecast_fn):
    """Per-step forecast errors of base_forecast_fn over past origins, from p_da[:h] only.

    An origin j is usable only if j + horizon <= h, so realized[j:j+horizon] is all past data.
    Returns an (m, horizon) array of (realized - forecast) vectors.
    """
    rows = []
    for j in range(1, max(0, h - horizon) + 1):
        fc = np.asarray(base_forecast_fn(p_da, j, horizon), dtype=float)
        if fc.size != horizon:
            continue
        realized = np.asarray(p_da[j:j + horizon], dtype=float)
        if realized.size != horizon:
            continue
        rows.append(realized - fc)
    if not rows:
        return np.zeros((0, horizon))
    return np.asarray(rows)


def _scenario_errors(errs, n_scenarios, horizon, rng):
    """Build n_scenarios error paths from the pool of past error vectors.

    With enough whole vectors, sample them with replacement (keeps the lookahead correlation).
    Early on, fall back to per-step quantiles; with no history the errors are zero, so the plan
    reduces to the certainty-equivalent one.
    """
    m = errs.shape[0]
    if m == 0:
        return np.zeros((n_scenarios, horizon))
    if m >= n_scenarios:
        pick = rng.integers(0, m, size=n_scenarios)
        return errs[pick]
    # Few samples: spread scenarios across per-step quantiles of the error at each lag.
    qs = np.linspace(0.05, 0.95, n_scenarios)
    out = np.empty((n_scenarios, horizon))
    for k in range(horizon):
        out[:, k] = np.quantile(errs[:, k], qs)
    return out


def _solve_two_stage_cvar(scenarios, par, e_current, alpha, terminal_prices):
    """Two-stage CVaR stochastic LP. Returns the shared (pch0, pdis0) here-and-now decision.

    scenarios       : (S, H) array of price paths [GBP/MWh]
    e_current       : SoC at the start of this hour [kWh]
    alpha           : CVaR level (worst (1-alpha) tail averaged)
    terminal_prices : length-S terminal valuation price per scenario [GBP/MWh] for leftover SoC
    """
    S, H = scenarios.shape
    dt = par.dt_h
    m = LpProblem("risk_mpc", LpMaximize)

    # first-stage trade, shared across scenarios
    pch0 = LpVariable("pch0", 0, par.p_max_kw)
    pdis0 = LpVariable("pdis0", 0, par.p_max_kw)

    eta = LpVariable("eta")                                   # the VaR level
    u = [LpVariable(f"u{s}", lowBound=0) for s in range(S)]   # tail shortfalls

    profit_s = []
    for s in range(S):
        price = scenarios[s]
        # per-scenario recourse for hours 1..H-1
        pch = [pch0] + [LpVariable(f"c{s}_{t}", 0, par.p_max_kw) for t in range(1, H)]
        pdis = [pdis0] + [LpVariable(f"d{s}_{t}", 0, par.p_max_kw) for t in range(1, H)]
        e = [LpVariable(f"E{s}_{t}", 0, par.e_cap_kwh) for t in range(H + 1)]

        m += e[0] == e_current
        for t in range(H):
            m += e[t + 1] == e[t] + par.eta_ch * pch[t] * dt - pdis[t] / par.eta_dis * dt

        # terminal value on leftover SoC so the plan doesn't dump the pack at the horizon edge
        arb = lpSum(price[t] * (pdis[t] - pch[t]) * dt / 1000.0 for t in range(H))
        arb = arb + terminal_prices[s] * e[H] / 1000.0
        profit_s.append(arb)
        # u_s >= eta - profit_s  (and u_s >= 0 by construction)
        m += u[s] >= eta - arb

    # Maximize CVaR_alpha = eta - 1/((1-alpha) S) * sum_s u_s
    m += eta - (1.0 / ((1.0 - alpha) * S)) * lpSum(u[s] for s in range(S))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m.solve(PULP_CBC_CMD(msg=0))
    assert LpStatus[m.status] == "Optimal", f"LP not optimal: {LpStatus[m.status]}"

    return float(value(pch0)), float(value(pdis0))


def run_risk_mpc(p_da, params: BatteryParams = BatteryParams(), horizon: int = 24,
                 n_scenarios: int = 7, alpha: float = 0.5,
                 base_forecast_fn=weekday_hour_average, seed: int = 0):
    """Rolling risk-aware (CVaR) MPC. Books day-ahead arbitrage at ACTUAL prices, zero reserve.

    Returns a dict shaped like run_mpc: charge_kw, discharge_kw, soc_kwh, profit_gbp.
    """
    par = params
    T = len(p_da)
    dt = par.dt_h
    rng = np.random.default_rng(seed)

    e = par.e0_kwh
    charge = np.zeros(T)
    discharge = np.zeros(T)
    soc = np.zeros(T + 1)
    soc[0] = e

    for h in range(T):
        if h == 0:                          # no price history yet: no trade
            soc[h + 1] = e
            continue

        base = np.asarray(base_forecast_fn(p_da, h, horizon), dtype=float)
        if base.size == 0:                  # defensive guard at the very end of the data
            base = np.asarray(p_da[h:h + 1], dtype=float)
        H = base.size

        errs = _past_step_errors(p_da, h, H, base_forecast_fn)
        err_paths = _scenario_errors(errs, n_scenarios, H, rng)
        scenarios = base[None, :] + err_paths               # (S, H) price paths
        terminal_prices = scenarios.mean(axis=1)            # per-scenario terminal price

        c0, d0 = _solve_two_stage_cvar(scenarios, par, e, alpha, terminal_prices)

        charge[h] = c0
        discharge[h] = d0
        e = e + par.eta_ch * c0 * dt - d0 / par.eta_dis * dt
        e = min(max(e, 0.0), par.e_cap_kwh)
        soc[h + 1] = e

    # book the committed first-hour trades at actual prices; no reserve revenue
    profit = float(np.sum(p_da * (discharge - charge) * dt / 1000.0))
    return {"charge_kw": charge, "discharge_kw": discharge, "soc_kwh": soc, "profit_gbp": profit}
