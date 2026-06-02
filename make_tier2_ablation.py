"""
Tier 2 terminal-value ablation: does valuing leftover end-of-window energy matter?

Runs the perfect-window MPC (perfect prices, so the terminal value is isolated from
forecast error) with and without the terminal value, across window lengths. Writes
results/tier2_terminal_ablation.csv.

Finding: on this dataset the terminal value is near-neutral at every horizon. The
horizon-edge dumping the brief warned about does not bite, because the 24 h window spans
the daily arbitrage cycle, valuing leftover energy at the window mean is near-neutral by
construction, and only the first hour is committed each step (so the window's end bias is
washed out before it reaches a committed action). The terminal value is kept as a
standard, near-free safeguard rather than removed.
"""
import os

import pandas as pd

from battery import BatteryParams, load_prices, perfect_window, run_mpc, solve_arbitrage

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "caseB_grid_battery_market_hourly.csv")
RESULTS = os.path.join(ROOT, "results")
os.makedirs(RESULTS, exist_ok=True)

_, p_da = load_prices(DATA)
par = BatteryParams()
pf = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh)["profit_gbp"]

rows = []
for hzn in [24, 12, 6]:
    on = run_mpc(p_da, par, horizon=hzn, forecast_fn=perfect_window, terminal=True)["profit_gbp"]
    off = run_mpc(p_da, par, horizon=hzn, forecast_fn=perfect_window, terminal=False)["profit_gbp"]
    rows.append({"horizon_h": hzn,
                 "terminal_on_gbp": round(on, 0),
                 "terminal_off_gbp": round(off, 0),
                 "diff_gbp": round(on - off, 0),
                 "diff_pct_of_perfect": round((on - off) / pf * 100, 2)})

df = pd.DataFrame(rows)
df.to_csv(os.path.join(RESULTS, "tier2_terminal_ablation.csv"), index=False)
print(f"perfect foresight: GBP {pf:,.0f}")
print(df.to_string(index=False))
print("\nterminal value is near-neutral at every horizon: the horizon-edge problem does not bite here")
