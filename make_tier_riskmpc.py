"""Does a risk-aware (CVaR) MPC recover the few percent a fixed reserve accidentally gave in the
realistic runs?

Compares, both at zero reserve and both on weekday_hour_average, the certainty-equivalent run_mpc
against run_risk_mpc. Also prints the fixed-500 reserve stack on the CE planner, so the anomaly the
reviewer points at sits next to the CVaR delta.
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

    recovers = delta > 0.0
    beats = risk_profit > ce_profit

    print("Risk-aware MPC vs certainty-equivalent, zero reserve, weekday_hour_average, "
          f"{len(p_da)} hours")
    print()
    print(f"CE-MPC (zero reserve)         : GBP {ce_profit:>10.2f}   [{t_ce:.1f}s]")
    print(f"Risk-MPC (CVaR, alpha=0.5)    : GBP {risk_profit:>10.2f}   [{t_risk:.1f}s]")
    print(f"  delta (risk - CE)           : GBP {delta:>10.2f}   ({100.0 * delta / ce_profit:+.2f}%)")
    print()
    print("Reference, the fixed-reserve anomaly:")
    print(f"CE-MPC + fixed-500 (arb only) : GBP {ce_res_profit:>10.2f}   [{t_ce_res:.1f}s]")
    print(f"  arbitrage uplift            : GBP {anomaly:>10.2f}   ({100.0 * anomaly / ce_profit:+.2f}%)")
    print(f"  + DC availability           : GBP {dc_avail:>10.2f}   (booked separately)")
    print()
    if beats:
        print("The CVaR plan beats the point-forecast plan at zero reserve, so the uplift is")
        print("forecast-uncertainty value the point forecast left on the table.")
    else:
        print("At zero reserve the CVaR plan does not beat the point-forecast plan, so the anomaly")
        print("is not recoverable this way. Kept as an honest negative.")

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
