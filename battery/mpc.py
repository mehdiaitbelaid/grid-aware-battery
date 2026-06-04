from __future__ import annotations

import numpy as np

from .arbitrage import BatteryParams, solve_arbitrage
from .forecast import same_hour_average


def run_mpc(p_da, params: BatteryParams = BatteryParams(), horizon: int = 24,
            forecast_fn=None, lookback_days: int = 7, terminal: bool = True,
            reserve_power_kw: float = 0.0, reserve_energy_kwh: float = 0.0):
    par = params
    T = len(p_da)
    dt = par.dt_h
    if forecast_fn is None:
        def forecast_fn(p, hh, hzn):
            return same_hour_average(p, hh, horizon=hzn, lookback_days=lookback_days)

    e = par.e0_kwh
    charge = np.zeros(T)
    discharge = np.zeros(T)
    soc = np.zeros(T + 1)
    soc[0] = e

    for h in range(T):
        if h == 0:                                        # no price history yet: no trade
            soc[h + 1] = e
            continue
        fc = np.asarray(forecast_fn(p_da, h, horizon), dtype=float)
        if fc.size == 0:                                  # defensive guard at the end of the data
            fc = np.asarray(p_da[h:h + 1], dtype=float)
        term = float(np.mean(fc)) if terminal else None
        plan = solve_arbitrage(fc, par, e_start=e, terminal_price=term,
                               reserve_power_kw=reserve_power_kw,
                               reserve_energy_kwh=reserve_energy_kwh)

        c0 = float(plan["charge_kw"][0])                  # commit only the first hour
        d0 = float(plan["discharge_kw"][0])
        charge[h] = c0
        discharge[h] = d0

        e = e + par.eta_ch * c0 * dt - d0 / par.eta_dis * dt
        e = min(max(e, 0.0), par.e_cap_kwh)
        soc[h + 1] = e

    # TODO: books day-ahead arbitrage only; reserve and imbalance revenue are not stacked yet
    profit = float(np.sum(p_da * (discharge - charge) * dt / 1000.0))
    return {"charge_kw": charge, "discharge_kw": discharge, "soc_kwh": soc, "profit_gbp": profit}
