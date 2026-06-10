"""Imbalance: the perfect-hindsight ceiling and what a persistence venue choice captures.

Prints the best-of ceiling, the day-ahead-only realistic profit, the two-price realistic profit,
and the difference.
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

    # only bank the two-price stack if it clears day-ahead by more than noise
    material = capture > 0 and capture >= 0.01 * abs(da_only)
    print()
    if material:
        print(f"Two-price venue choice adds GBP {capture:,.0f} over day-ahead only.")
    else:
        print(f"Two-price venue choice adds only GBP {capture:,.0f} over day-ahead only, "
              f"inside the noise.")
        print("The ceiling stands as a perfect-hindsight upper bound.")


if __name__ == "__main__":
    main()
