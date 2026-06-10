"""Risk-aware (CVaR) model-predictive control for the day-ahead arbitrage battery.

This module tests one specific reviewer claim. In the realistic (forecast-driven) MPC runs,
adding a fixed reserve obligation sometimes *raises* the booked day-ahead profit instead of
lowering it. The reviewer argues this is not a real "reserve helps trading" effect but
certainty-equivalent overtrading: a point-forecast plan commits aggressive first-hour trades
that are sometimes wrong, and the reserve constraint accidentally tempers them. If that is the
mechanism, a plan that prices forecast uncertainty on purpose (a CVaR plan) should capture the
same few percent without needing any reserve constraint, and at zero reserve.

The design follows the task spec exactly:

  * Rolling MPC. Each hour h we look only at p_da[:h] (strictly leakage-free).
  * We build n_scenarios horizon-length price paths = base point forecast + additive error
    vectors sampled from the EMPIRICAL distribution of this forecaster's own past errors,
    measured on p_da[:h] only.
  * We solve a TWO-STAGE stochastic LP: the first-hour charge/discharge (pch0, pdis0) is shared
    across every scenario (here-and-now), and every later hour gets its own per-scenario recourse
    decision and per-scenario SoC trajectory, all starting from the same e_current.
  * The objective is the CVaR at level alpha of the per-scenario profits (the worst-tail
    average), with the standard linearization
        eta - 1/((1-alpha)*S) * sum_s u_s ,   u_s >= eta - profit_s ,  u_s >= 0.
  * We commit the shared first hour and book it at the ACTUAL p_da[h]. h=0: no trade.

Nothing here touches existing files. Import directly:  from battery.risk_mpc import run_risk_mpc
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
    """Empirical per-step forecast errors of base_forecast_fn, measured on p_da[:h] only.

    For every past origin j where both the forecast and its realized outcome lie fully inside
    p_da[:h], record the error vector (realized - forecast) of length `horizon`. Returns an
    (m, horizon) array of error vectors; m is the number of usable past origins.

    Leakage guard: an origin j is usable only if j + horizon <= h, so realized[j:j+horizon] is
    entirely strictly-past data. The forecaster itself also reads only p_da[:j] by contract.
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
    """Turn the pool of past per-step error vectors into n_scenarios error paths.

    Two regimes, both strictly from past data:
      * Enough whole past error vectors -> sample n_scenarios of them with replacement. This keeps
        the natural correlation along the lookahead (an error path that drifts high stays high).
      * Too few (early in the series) -> fall back to per-step quantiles. Build n_scenarios paths
        whose k-th entry is a quantile of the per-step error at lag k, spanning the spread. With
        zero history this yields all-zero errors, so the scenarios collapse to the point forecast
        and the stochastic LP reduces to the certainty-equivalent plan.
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

    # First-stage (here-and-now), shared across every scenario.
    pch0 = LpVariable("pch0", 0, par.p_max_kw)
    pdis0 = LpVariable("pdis0", 0, par.p_max_kw)

    # CVaR auxiliaries.
    eta = LpVariable("eta")                                   # free: the VaR level
    u = [LpVariable(f"u{s}", lowBound=0) for s in range(S)]   # tail shortfalls

    profit_s = []
    for s in range(S):
        price = scenarios[s]
        # Second-stage recourse: per-scenario charge/discharge for hours 1..H-1 plus the SoC path.
        pch = [pch0] + [LpVariable(f"c{s}_{t}", 0, par.p_max_kw) for t in range(1, H)]
        pdis = [pdis0] + [LpVariable(f"d{s}_{t}", 0, par.p_max_kw) for t in range(1, H)]
        e = [LpVariable(f"E{s}_{t}", 0, par.e_cap_kwh) for t in range(H + 1)]

        m += e[0] == e_current
        for t in range(H):
            m += e[t + 1] == e[t] + par.eta_ch * pch[t] * dt - pdis[t] / par.eta_dis * dt

        # Arbitrage value of this scenario plus a terminal value on leftover SoC, so the planner
        # is not pushed to dump the battery at the horizon edge (same device the CE-MPC uses).
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

        # Empirical error paths for this forecaster, from strictly-past data only.
        errs = _past_step_errors(p_da, h, H, base_forecast_fn)
        err_paths = _scenario_errors(errs, n_scenarios, H, rng)
        scenarios = base[None, :] + err_paths               # (S, H) price paths

        # Per-scenario terminal price: mean of that scenario's own path (matches CE-MPC's terminal).
        terminal_prices = scenarios.mean(axis=1)

        c0, d0 = _solve_two_stage_cvar(scenarios, par, e, alpha, terminal_prices)

        charge[h] = c0
        discharge[h] = d0
        e = e + par.eta_ch * c0 * dt - d0 / par.eta_dis * dt
        e = min(max(e, 0.0), par.e_cap_kwh)
        soc[h + 1] = e

    # Book the committed first-hour trades at the ACTUAL day-ahead prices. Zero reserve revenue.
    profit = float(np.sum(p_da * (discharge - charge) * dt / 1000.0))
    return {"charge_kw": charge, "discharge_kw": discharge, "soc_kwh": soc, "profit_gbp": profit}
