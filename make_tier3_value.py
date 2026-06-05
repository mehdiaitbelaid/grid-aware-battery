# Net value of holding 500 kW as DC reserve. Revenue uses the availability price that ships in the
# dataset (ancillary_availability_gbp_per_mw_per_h), not a hand-picked sweep. 500 kW is below the
# 1 MW DC minimum, so read it as a share of an aggregated fleet. The defensible headline is the net
# against the perfect-foresight cost of reserving: single basis, no noise term.
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from battery import BatteryParams, load_prices, solve_arbitrage

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "caseB_grid_battery_market_hourly.csv")
RESULTS = os.path.join(ROOT, "results")
PLOTS = os.path.join(ROOT, "plots")
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(PLOTS, exist_ok=True)

RESERVE_KW = 500.0
RESERVE_MW = RESERVE_KW / 1000.0
DUR_H = 0.5
HOURS = 1440                                   # 60 days of the price series

df, p_da = load_prices(DATA)
avail = df["ancillary_availability_gbp_per_mw_per_h"].to_numpy()[:HOURS]
par = BatteryParams()

# arbitrage forgone by reserving 500 kW, perfect foresight: the upper bound on the cost
base = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh)["profit_gbp"]
res = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
                      reserve_power_kw=RESERVE_KW,
                      reserve_energy_kwh=RESERVE_KW * DUR_H / par.eta_dis)["profit_gbp"]
cost_perfect = base - res

# realistic-forecast cost, interpolated to 50% from the sensitivity sweep. The raw value is slightly
# negative (reserve acts as a guardrail on an overconfident forecast), which the sensitivity section
# flags as within forecast noise. I floor it at zero rather than bank it as a gain.
sens = pd.read_csv(os.path.join(RESULTS, "tier3_pareto_sensitivity.csv"))
r0 = float(sens.loc[sens.reserve_pct == 0, "realistic_gbp"].iloc[0])
r50 = float(np.interp(50, sens.reserve_pct, sens.realistic_gbp))
cost_realistic_raw = r0 - r50
cost_realistic = max(cost_realistic_raw, 0.0)

# DC availability revenue from the actual hourly series, and the break-even price
dc_revenue = RESERVE_MW * float(avail.sum())   # GBP over 60 days, paid per MW per hour held
mean_price = float(avail.mean())
breakeven = cost_perfect / (RESERVE_MW * HOURS)
net_perfect = dc_revenue - cost_perfect        # conservative, single-basis headline
net_realistic = dc_revenue - cost_realistic    # realistic reserve cost is about zero, so this is ~the DC revenue

pd.DataFrame([{"dc_mean_price_gbp_per_mw_h": round(mean_price, 2),
               "dc_revenue_gbp": round(dc_revenue, 0),
               "arbitrage_cost_perfect_gbp": round(cost_perfect, 0),
               "arbitrage_cost_realistic_raw_gbp": round(cost_realistic_raw, 0),
               "arbitrage_cost_realistic_floored_gbp": round(cost_realistic, 0),
               "breakeven_perfect_gbp_per_mw_h": round(breakeven, 2),
               "net_vs_perfect_gbp": round(net_perfect, 0),
               "net_realistic_gbp": round(net_realistic, 0)}]).to_csv(
    os.path.join(RESULTS, "tier3_value.csv"), index=False)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
ax1.plot(avail, lw=0.6, color="#999999", alpha=0.8, label="hourly price")
ax1.axhline(mean_price, color="#2ca02c", lw=1.7, label=f"data mean {mean_price:.2f}")
ax1.axhline(breakeven, ls=":", color="purple", lw=1.5, label=f"break-even {breakeven:.2f} (perfect foresight)")
ax1.set_xlabel("hour")
ax1.set_ylabel("DC availability price (GBP/MW/h)")
ax1.set_title("DC availability price and break-even")
ax1.legend(loc="upper right", fontsize=8.5)
ax1.grid(alpha=0.3)

labels = ["net of perfect\nforesight cost", "net of realistic\ncost (about 0)"]
vals = [net_perfect, net_realistic]
bars = ax2.bar(labels, vals, color=["#1f6feb", "#2ca02c"], alpha=0.85)
ax2.axhline(0.0, color="black", lw=0.8)
for b, v in zip(bars, vals):
    ax2.text(b.get_x() + b.get_width() / 2, v + 80, f"GBP {v:+,.0f}", ha="center", fontsize=9)
ax2.set_ylabel("Net value over 60 days (GBP)")
ax2.set_title("Net value of 500 kW reserve at the data DC price")
ax2.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier3_value.png"), dpi=150)
plt.close(fig)

print(f"DC availability price (data): mean {mean_price:.2f} GBP/MW/h, range {avail.min():.2f} to {avail.max():.2f}")
print(f"reserve revenue, 0.5 MW:      GBP {dc_revenue:,.0f}")
print(f"cost of reserving 500 kW:     GBP {cost_perfect:,.0f} perfect foresight; realistic raw GBP {cost_realistic_raw:,.0f} (within noise, floored to 0)")
print(f"break-even DC price:          {breakeven:.2f} GBP/MW/h (perfect foresight)")
print(f"net value:                    GBP {net_perfect:+,.0f} vs perfect-foresight cost; GBP {net_realistic:+,.0f} under a realistic forecast")
