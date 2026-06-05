import os

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from battery import BatteryParams, load_prices, run_mpc, same_hour_average, solve_arbitrage

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "caseB_grid_battery_market_hourly.csv")
RESULTS = os.path.join(ROOT, "results")
PLOTS = os.path.join(ROOT, "plots")
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(PLOTS, exist_ok=True)

DURATION_H = 0.5

_, p_da = load_prices(DATA)
par = BatteryParams()

rows = []
for frac in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
    p_res = frac * par.p_max_kw
    e_floor = p_res * DURATION_H / par.eta_dis
    perfect = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
                              reserve_power_kw=p_res, reserve_energy_kwh=e_floor)["profit_gbp"]
    realistic = run_mpc(p_da, par, forecast_fn=same_hour_average,
                        reserve_power_kw=p_res, reserve_energy_kwh=e_floor)["profit_gbp"]
    rows.append({"reserve_pct": round(frac * 100), "reserve_kw": round(p_res),
                 "perfect_gbp": round(perfect, 0), "realistic_gbp": round(realistic, 0)})
    print(f"reserve {int(frac * 100):3d}%   perfect {perfect:8.0f}   realistic {realistic:8.0f}",
          flush=True)

df = pd.DataFrame(rows)
pbase = df.loc[df.reserve_pct == 0, "perfect_gbp"].iloc[0]
rbase = df.loc[df.reserve_pct == 0, "realistic_gbp"].iloc[0]
df["perfect_pct"] = (df["perfect_gbp"] / pbase * 100).round(1)
df["realistic_pct"] = (df["realistic_gbp"] / rbase * 100).round(1)
df.to_csv(os.path.join(RESULTS, "tier3_pareto_sensitivity.csv"), index=False)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
ax1.plot(df["reserve_kw"], df["perfect_gbp"], "o-", lw=1.9, color="#1f6feb", label="perfect foresight")
ax1.plot(df["reserve_kw"], df["realistic_gbp"], "s-", lw=1.9, color="#d29922", label="realistic forecast (MPC)")
ax1.set_xlabel("Reserved response power (kW)")
ax1.set_ylabel("Arbitrage profit over 60 days (GBP)")
ax1.set_title("Absolute arbitrage profit vs reserved power")
ax1.legend()
ax1.grid(alpha=0.3)
ax2.plot(df["reserve_kw"], df["perfect_pct"], "o-", lw=1.9, color="#1f6feb", label="perfect foresight")
ax2.plot(df["reserve_kw"], df["realistic_pct"], "s-", lw=1.9, color="#d29922", label="realistic forecast (MPC)")
ax2.set_xlabel("Reserved response power (kW)")
ax2.set_ylabel("Profit kept (% of own 0% reserve)")
ax2.set_title("Normalised profit kept by reserve level")
ax2.legend()
ax2.grid(alpha=0.3)
fig.suptitle("Tier 3 reserve frontier: theoretical (perfect foresight) vs operational (real forecast)")
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier3_pareto_sensitivity.png"), dpi=150)
plt.close(fig)

print(f"\nperfect baseline (0%):   GBP {pbase:,.0f}   (Stage 1 reference)")
print(f"realistic baseline (0%): GBP {rbase:,.0f}   (Tier 2 same-hour reference: 3,927)")
print(df.to_string(index=False))
