"""AR(1)-on-residuals forecaster vs the weekday baseline, measured on day-ahead arbitrage."""
from __future__ import annotations

import os

import numpy as np

from battery import BatteryParams, load_prices, run_mpc
from battery.forecast import weekday_hour_average
from battery.ar1_forecast import weekday_hour_ar1, _fixed_effects

DATA = os.path.join(os.path.dirname(__file__), "data", "caseB_grid_battery_market_hourly.csv")


def representative_phi(series, h: int):
    """Reproduce the phi that weekday_hour_ar1 would estimate at hour h."""
    series = np.asarray(series, dtype=float)
    past = series[:h]
    g, he, de = _fixed_effects(past)
    t = np.arange(h)
    resid = past - (g + he[t % 24] + de[(t // 24) % 7])
    r0, r1 = resid[:-1], resid[1:]
    denom = float(np.dot(r0, r0))
    phi_hat = float(np.dot(r0, r1) / denom) if denom > 0.0 else 0.0
    return float(np.clip(phi_hat, 0.0, 0.95))


def leakage_check(p_da):
    """Corrupting the future must not change the forecast for an early hour."""
    h = 100                                   # an early hour, past the h<72 fallback boundary
    clean = weekday_hour_ar1(p_da, h, horizon=24)
    corrupted = p_da.copy().astype(float)
    corrupted[h:] = -1e6                      # poison everything from h onward
    poisoned = weekday_hour_ar1(corrupted, h, horizon=24)
    ok = np.allclose(clean, poisoned)
    max_abs = float(np.max(np.abs(clean - poisoned)))
    return ok, max_abs, h


def main():
    df, p_da = load_prices(DATA)
    par = BatteryParams()

    base = run_mpc(p_da, par, forecast_fn=weekday_hour_average)["profit_gbp"]
    ar1 = run_mpc(p_da, par, forecast_fn=weekday_hour_ar1)["profit_gbp"]
    delta = ar1 - base
    delta_pct = 100.0 * delta / base if base != 0 else float("nan")

    # A representative phi: use the full-history fit (h = len), the most informed estimate.
    phi_rep = representative_phi(p_da, len(p_da))
    # Also report the median phi across the rolling MPC re-plans, so the number is honest.
    phis = [representative_phi(p_da, h) for h in range(72, len(p_da))]
    phi_median = float(np.median(phis))

    ok, max_abs, hcheck = leakage_check(p_da)

    print("=== Tier 2 AR(1)-on-residuals day-ahead forecaster ===")
    print(f"weekday_hour_average profit : GBP {base:,.0f}")
    print(f"weekday_hour_ar1     profit : GBP {ar1:,.0f}")
    print(f"delta                       : GBP {delta:,.0f}")
    print(f"delta_pct                   : {delta_pct:+.3f} %")
    print(f"representative phi (h=full) : {phi_rep:.4f}")
    print(f"median phi over MPC replans : {phi_median:.4f}")
    print()
    print("=== Leakage check (corrupt the future, forecast an early hour) ===")
    print(f"hour checked                : {hcheck}")
    print(f"forecast unchanged          : {ok}")
    print(f"max abs diff                : {max_abs:.3e}")
    print()

    if ar1 > base:
        print(f"AR(1) beats the weekday baseline by GBP {delta:,.0f}.")
    else:
        print(f"AR(1) does not beat the weekday baseline (GBP {delta:,.0f}).")


if __name__ == "__main__":
    main()
