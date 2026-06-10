"""Tier driver: does a risk-aware (CVaR) MPC recover the few percent that a fixed reserve
accidentally captured in the realistic runs?

Reviewer claim under test: the "realistic profit rises when you add reserve" anomaly is
certainty-equivalent overtrading. A point-forecast MPC commits aggressive first-hour trades that
are sometimes wrong; a reserve constraint accidentally tempers them and the booked profit ticks
up. If that is the real mechanism, a CVaR plan that prices the forecaster's own past errors on
purpose should capture the same uplift at ZERO reserve.

We compare, both at zero reserve and both driven by weekday_hour_average:
  * CE baseline   : run_mpc(p_da, par, forecast_fn=weekday_hour_average)
  * Risk-aware    : run_risk_mpc(p_da, par, base_forecast_fn=weekday_hour_average)

We also print the fixed-500 reserve stack on the SAME CE planner, so the size of the anomaly the
reviewer is pointing at is visible next to the CVaR delta.

Run:  .venv/bin/python make_tier_riskmpc.py
"""

from __future__ import annotations

import time
import warnings

import numpy as np

from battery import BatteryParams, load_prices, run_mpc
from battery.forecast import weekday_hour_average
from battery.risk_mpc import run_risk_mpc

DATA = "data/caseB_grid_battery_market_hourly.csv"


def main():
    df, p_da = load_prices(DATA)
    par = BatteryParams()
    avail = df["ancillary_availability_gbp_per_mw_per_h"].to_numpy()

    # Certainty-equivalent baseline, zero reserve.
    t0 = time.time()
    ce = run_mpc(p_da, par, horizon=24, forecast_fn=weekday_hour_average)
    t_ce = time.time() - t0
    ce_profit = ce["profit_gbp"]

    # The anomaly the reviewer names: CE planner with the fixed-500 reserve obligation, same run.
    eta_dis = par.eta_dis
    res_p = 500.0
    res_e = 500.0 * 0.5 / eta_dis
    t0 = time.time()
    ce_res = run_mpc(p_da, par, horizon=24, forecast_fn=weekday_hour_average,
                     reserve_power_kw=res_p, reserve_energy_kwh=res_e)
    t_ce_res = time.time() - t0
    ce_res_profit = ce_res["profit_gbp"]
    dc_avail = 0.5 * float(np.sum(avail))            # availability revenue the reserve would also earn

    # Risk-aware CVaR MPC, zero reserve, same forecaster.
    t0 = time.time()
    risk = run_risk_mpc(p_da, par, horizon=24, n_scenarios=7, alpha=0.5,
                        base_forecast_fn=weekday_hour_average)
    t_risk = time.time() - t0
    risk_profit = risk["profit_gbp"]

    delta = risk_profit - ce_profit
    anomaly = ce_res_profit - ce_profit              # arbitrage-only uplift the reserve accidentally gave

    print("=" * 64)
    print("Risk-aware MPC vs certainty-equivalent MPC  (zero reserve, both)")
    print("Forecaster: weekday_hour_average   Horizon: 24   Hours: %d" % len(p_da))
    print("=" * 64)
    print(f"CE-MPC profit (zero reserve)          : GBP {ce_profit:>12.2f}   [{t_ce:5.1f}s]")
    print(f"Risk-MPC profit (CVaR, alpha=0.5)     : GBP {risk_profit:>12.2f}   [{t_risk:5.1f}s]")
    print(f"  delta (risk - CE)                   : GBP {delta:>12.2f}"
          f"  ({100.0 * delta / ce_profit:+.2f}%)")
    print("-" * 64)
    print("Reference: the anomaly the reviewer is pointing at")
    print(f"CE-MPC + fixed-500 reserve (arb only) : GBP {ce_res_profit:>12.2f}   [{t_ce_res:5.1f}s]")
    print(f"  reserve arbitrage-only uplift       : GBP {anomaly:>12.2f}"
          f"  ({100.0 * anomaly / ce_profit:+.2f}%)")
    print(f"  (+ DC availability revenue          : GBP {dc_avail:>12.2f}  booked separately)")
    print("-" * 64)
    recovers = delta > 0.0
    beats = risk_profit > ce_profit
    print(f"Risk-MPC beats CE-MPC?                 : {beats}")
    print(f"Recovers the reserve anomaly on purpose?: {recovers and delta >= 0.5 * anomaly}")
    print("=" * 64)
    if beats:
        print("RECOMMENDATION: SHIP. The CVaR plan beats the certainty-equivalent plan at zero")
        print("reserve, which supports the reviewer: the uplift is forecast-uncertainty value")
        print("the point-forecast planner was leaving on the table, not a reserve effect.")
    else:
        print("RECOMMENDATION: DO NOT SHIP as a profit win. At zero reserve the CVaR plan does not")
        print("beat the certainty-equivalent plan on booked day-ahead profit, so it does not")
        print("reproduce the reserve anomaly as deliberate risk-aware value. Keep it only as the")
        print("honest negative control that the anomaly is not simply recoverable this way.")

    return {
        "ce_mpc_gbp": round(ce_profit, 2),
        "risk_mpc_gbp": round(risk_profit, 2),
        "delta_gbp": round(delta, 2),
        "ce_res_gbp": round(ce_res_profit, 2),
        "anomaly_gbp": round(anomaly, 2),
        "recovers": bool(recovers),
        "ship": bool(beats),
    }


if __name__ == "__main__":
    out = main()
