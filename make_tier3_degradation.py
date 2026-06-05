# Degradation sensitivity: a throughput cost in GBP per MWh discharged makes arbitrage less
# valuable and shifts the 500 kW frequency reserve break even. Perfect foresight, so this is the
# theoretical frontier, the same basis as the Stage 1 reserve study. The cost is uncertain, so I
# sweep it rather than bake one number into the baseline.
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
HOURS = 1440                              # 60 days of the price series
COSTS = [0.0, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0]   # GBP per MWh discharged; ~10 is a central estimate

_, p_da = load_prices(DATA)
par = BatteryParams()
e_floor = RESERVE_KW * DUR_H / par.eta_dis

rows = []
for c in COSTS:
    base = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
                           degradation_cost_per_mwh=c)
    res = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
                          reserve_power_kw=RESERVE_KW, reserve_energy_kwh=e_floor,
                          degradation_cost_per_mwh=c)
    cost_reserve = base["profit_gbp"] - res["profit_gbp"]
    breakeven = cost_reserve / (RESERVE_MW * HOURS)
    throughput_mwh = float(base["discharge_kw"].sum()) * par.dt_h / 1000.0
    rows.append({"deg_cost_gbp_per_mwh": c,
                 "arbitrage_gbp": round(base["profit_gbp"], 0),
                 "throughput_mwh": round(throughput_mwh, 1),
                 "reserve_cost_gbp": round(cost_reserve, 0),
                 "breakeven_dc_gbp_per_mw_h": round(breakeven, 2)})
    print(f"deg {c:5.1f} GBP/MWh -> arbitrage GBP {base['profit_gbp']:8,.0f}, "
          f"throughput {throughput_mwh:7,.0f} MWh, break even {breakeven:5.2f} GBP/MW/h", flush=True)

df = pd.DataFrame(rows)
df.to_csv(os.path.join(RESULTS, "tier3_degradation.csv"), index=False)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
ax1.plot(df["deg_cost_gbp_per_mwh"], df["arbitrage_gbp"], "o-", lw=1.9, color="#1f6feb")
ax1.set_xlabel("Degradation cost (GBP per MWh discharged)")
ax1.set_ylabel("Perfect foresight arbitrage over 60 days (GBP)")
ax1.set_title("Arbitrage profit vs degradation cost")
ax1.grid(alpha=0.3)
ax2.plot(df["deg_cost_gbp_per_mwh"], df["breakeven_dc_gbp_per_mw_h"], "s-", lw=1.9, color="#2ca02c")
ax2.axvline(10.0, ls=":", color="#888888", lw=1.1, label="central estimate, about 10 GBP/MWh")
ax2.set_xlabel("Degradation cost (GBP per MWh discharged)")
ax2.set_ylabel("Break even DC price (GBP/MW/h)")
ax2.set_title("Reserve break-even vs degradation cost")
ax2.legend(loc="upper right", fontsize=9)
ax2.grid(alpha=0.3)
fig.suptitle("Tier 3 degradation sensitivity: throughput cost on the 500 kW reserve break even (perfect foresight)")
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier3_degradation.png"), dpi=150)
plt.close(fig)

b0 = rows[0]
b10 = df.loc[df.deg_cost_gbp_per_mwh == 10.0].iloc[0]
print(f"\nbaseline (0 cost):   arbitrage GBP {b0['arbitrage_gbp']:,.0f}, break even {b0['breakeven_dc_gbp_per_mw_h']:.2f} GBP/MW/h")
print(f"at 10 GBP/MWh:       arbitrage GBP {b10['arbitrage_gbp']:,.0f}, break even {b10['breakeven_dc_gbp_per_mw_h']:.2f} GBP/MW/h")
