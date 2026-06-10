"""Imbalance tier driver.

Prints, in order:
  1. bestof_bound          perfect-hindsight CEILING (labeled, not achievable)
  2. da_only_realistic     run_mpc on the weekday_hour_average forecast, settled at day-ahead
  3. twoprice_realistic    same dispatch, per-hour venue choice via leakage-free persistence
  4. capture               twoprice_realistic minus da_only_realistic

The bound ships either way as a labeled ceiling. The two-price run ships ONLY if it clearly
beats the da-only run; otherwise it is reported honestly as tried, captured ~X, not worth
shipping.
"""

from __future__ import annotations

from battery import BatteryParams, load_prices, run_mpc
from battery.forecast import weekday_hour_average
from battery.imbalance import bestof_bound, run_twoprice_mpc

DATA = "data/caseB_grid_battery_market_hourly.csv"


def main() -> None:
    df, p_da = load_prices(DATA)
    imb = df["imbalance_price_gbp_per_mwh"].to_numpy()
    par = BatteryParams()

    bound = bestof_bound(p_da, imb, par)
    da_only = run_mpc(p_da, par, horizon=24, forecast_fn=weekday_hour_average)["profit_gbp"]
    twoprice = run_twoprice_mpc(p_da, imb, par, horizon=24)["profit_gbp"]
    capture = twoprice - da_only

    print(f"bestof_bound (perfect-hindsight CEILING, not achievable): GBP {bound:,.0f}")
    print(f"da_only_realistic  (run_mpc, weekday_hour_average):       GBP {da_only:,.0f}")
    print(f"twoprice_realistic (persistence venue choice):            GBP {twoprice:,.0f}")
    print(f"realistic_capture  (twoprice - da_only):                  GBP {capture:,.0f}")

    # Ship the two-price stack only if it clearly beats da-only. "Clearly" here means a
    # positive capture that is material against the da-only base, not a rounding wobble.
    clearly_beats = capture > 0 and capture >= 0.01 * abs(da_only)
    print()
    if clearly_beats:
        print(f"RECOMMENDATION: ship_realistic=true. The two-price stack captures "
              f"GBP {capture:,.0f} over da-only, a real gain worth shipping.")
    else:
        print(f"RECOMMENDATION: ship_realistic=false. Tried the two-price stack, captured "
              f"GBP {capture:,.0f} over da-only, not worth shipping.")
        print("The bestof_bound still ships as a labeled perfect-hindsight ceiling.")


if __name__ == "__main__":
    main()
