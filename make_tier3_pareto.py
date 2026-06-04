import os

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

DURATION_H = 0.5   # 30-minute sustain requirement for the reserved response

_, p_da = load_prices(DATA)
par = BatteryParams()

rows = []
for frac in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
    p_res = frac * par.p_max_kw
    e_floor = p_res * DURATION_H / par.eta_dis        # stored energy to sustain p_res for DURATION_H
    out = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
                          reserve_power_kw=p_res, reserve_energy_kwh=e_floor)
    rows.append({"reserve_pct": round(frac * 100),
                 "reserve_kw": round(p_res),
                 "reserve_energy_kwh": round(e_floor, 1),
                 "profit_gbp": round(out["profit_gbp"], 0)})

df = pd.DataFrame(rows)
base = df.loc[df.reserve_pct == 0, "profit_gbp"].iloc[0]
df["profit_pct_of_base"] = (df["profit_gbp"] / base * 100).round(1)
df["profit_sacrificed_gbp"] = (base - df["profit_gbp"]).round(0)
df.to_csv(os.path.join(RESULTS, "tier3_pareto.csv"), index=False)

fig, ax = plt.subplots(figsize=(8.5, 5.2))
ax.plot(df["reserve_kw"], df["profit_gbp"], "o-", lw=1.9, color="#1f6feb")
ax.set_xlabel("Frequency-response power reserved (kW)")
ax.set_ylabel("Arbitrage profit over 60 days (GBP)")
ax.set_title("Tier 3: the price of reliability\n"
             "arbitrage profit vs reserved response capacity (30 min sustain, perfect foresight)")
ax.grid(alpha=0.3)
for _, r in df.iterrows():
    if r.reserve_pct in (0, 50, 100):
        ax.annotate(f"{int(r.reserve_pct)}%", (r.reserve_kw, r.profit_gbp),
                    textcoords="offset points", xytext=(6, 8), fontsize=9)
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier3_pareto.png"), dpi=150)
plt.close(fig)

print(f"baseline (0% reserve): GBP {base:,.0f}   (Tier 2 perfect-foresight reference: 16,176)")
print(df.to_string(index=False))
