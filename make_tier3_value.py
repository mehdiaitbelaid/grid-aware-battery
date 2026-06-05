# Net value: DC availability revenue on the reserved 500 kW against the arbitrage it costs.
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
HOURS = 1440                       # 60 days of the price series

_, p_da = load_prices(DATA)
par = BatteryParams()

# perfect-foresight arbitrage cost of holding 500 kW back
base = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh)["profit_gbp"]
res = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
                      reserve_power_kw=RESERVE_KW,
                      reserve_energy_kwh=RESERVE_KW * DUR_H / par.eta_dis)["profit_gbp"]
cost_perfect = base - res

# realistic-forecast cost, interpolated to 50% from the committed sensitivity sweep
sens = pd.read_csv(os.path.join(RESULTS, "tier3_pareto_sensitivity.csv"))
r0 = float(sens.loc[sens.reserve_pct == 0, "realistic_gbp"].iloc[0])
r50 = float(np.interp(50, sens.reserve_pct, sens.realistic_gbp))
cost_realistic = r0 - r50          # near zero: the reserve is nearly free under a weak forecast

# DC availability revenue and net value across clearing prices
prices = np.linspace(0.0, 20.0, 81)
revenue = RESERVE_MW * prices * HOURS
net_perfect = revenue - cost_perfect
net_realistic = revenue - cost_realistic
breakeven = cost_perfect / (RESERVE_MW * HOURS)

pd.DataFrame({"dc_price_gbp_per_mw_h": prices,
              "dc_revenue_gbp": np.round(revenue, 0),
              "net_vs_perfect_gbp": np.round(net_perfect, 0),
              "net_vs_realistic_gbp": np.round(net_realistic, 0)}).to_csv(
    os.path.join(RESULTS, "tier3_value.csv"), index=False)

fig, ax = plt.subplots(figsize=(8.6, 5.0))
ax.axhline(0.0, color="black", lw=0.8)
ax.axvline(breakeven, ls=":", color="purple", lw=1.1, alpha=0.7,
           label=f"break-even {breakeven:.1f} GBP/MW/h (perfect foresight)")
ax.plot(prices, net_perfect, lw=1.9, color="#1f6feb", label="net value vs perfect foresight cost")
ax.plot(prices, net_realistic, lw=1.9, color="#2ca02c",
        label="net value vs realistic forecast cost (reserve nearly free)")
ax.set_xlabel("DC availability price (GBP/MW/h)")
ax.set_ylabel("Net value over 60 days (GBP)")
ax.set_title("Tier 3 net value: DC revenue on 500 kW reserved minus arbitrage forgone\n"
             "price-dependent against perfect foresight, almost pure profit for a real operator")
ax.legend(loc="upper left", fontsize=8.5)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier3_value.png"), dpi=150)
plt.close(fig)

print(f"arbitrage forgone reserving 500 kW, perfect foresight: GBP {cost_perfect:,.0f}")
print(f"arbitrage forgone, realistic forecast:                 GBP {cost_realistic:,.0f} (nearly free)")
print(f"break-even DC price vs perfect foresight:              {breakeven:.2f} GBP/MW/h")
for P in (5, 10, 15):
    print(f"  DC {P:2d} GBP/MW/h -> revenue GBP {RESERVE_MW * P * HOURS:6,.0f}, "
          f"net vs perfect GBP {RESERVE_MW * P * HOURS - cost_perfect:+7,.0f}")
