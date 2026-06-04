"""
Tier 2 deliverables: the perfect foresight vs rolling-horizon MPC comparison, and the
profit-versus-forecast-quality sweep (the value of information).

Writes results/tier2_mpc.csv, plots/tier2_decomposition.png, plots/tier2_forecast_value.png.
The MPC calls the LP solver about 1440 times per run, so the full script takes a couple
of minutes.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from battery import (BatteryParams, load_prices, solve_arbitrage, run_mpc,
                     perfect_window, persistence, perfect_plus_noise)

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "caseB_grid_battery_market_hourly.csv")
RESULTS = os.path.join(ROOT, "results")
PLOTS = os.path.join(ROOT, "plots")
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(PLOTS, exist_ok=True)

_, p_da = load_prices(DATA)
par = BatteryParams()

pf = solve_arbitrage(p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh)["profit_gbp"]
pw = run_mpc(p_da, par, forecast_fn=perfect_window)["profit_gbp"]
ps = run_mpc(p_da, par, forecast_fn=persistence)["profit_gbp"]
sh = run_mpc(p_da, par)["profit_gbp"]                 # same-hour average (the chosen forecast)

sigmas = [0, 5, 10, 20, 40, 80]
sweep = []
for s in sigmas:
    fc = (lambda p, h, H, ss=s: perfect_plus_noise(p, h, H, sigma=ss, seed=0))
    sweep.append(run_mpc(p_da, par, forecast_fn=fc)["profit_gbp"])

# ---- plot 1: the decomposition ----
labels = ["perfect\nforesight", "MPC\nperfect window", "MPC\nsame-hour avg", "MPC\npersistence"]
vals = [pf, pw, sh, ps]
colors = ["tab:green", "tab:olive", "tab:blue", "tab:gray"]
fig, ax = plt.subplots(figsize=(8, 5))
bars = ax.bar(labels, vals, color=colors, alpha=0.85)
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, v + 200,
            f"GBP {v:,.0f}\n{v / pf * 100:.0f}%", ha="center", fontsize=9)
ax.set_ylabel("60-day arbitrage profit (GBP)")
ax.set_title("Tier 2: perfect foresight vs rolling-horizon MPC\n"
             "2 MWh / 1 MW battery, 60 days of GB day-ahead prices")
ax.set_ylim(0, pf * 1.18)
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier2_decomposition.png"), dpi=150)
plt.close(fig)

# ---- plot 2: the value of forecast quality ----
fig, ax = plt.subplots(figsize=(8.5, 5))
pct = [v / pf * 100 for v in sweep]
ax.plot(sigmas, pct, "o-", color="tab:purple", lw=2,
        label="synthetic forecast (truth + growing noise)")
ax.axhline(sh / pf * 100, ls="--", color="tab:blue", lw=1.3,
           label=f"same-hour average ({sh / pf * 100:.0f}%)")
ax.axhline(ps / pf * 100, ls="--", color="tab:gray", lw=1.3,
           label=f"persistence ({ps / pf * 100:.0f}%)")
ax.set_xlabel("forecast noise at 1 h ahead, sigma (GBP/MWh), growing with lead time")
ax.set_ylabel("MPC profit (% of perfect foresight)")
ax.set_title("Tier 2 bonus: the value of forecast quality\n"
             "profit falls smoothly as forecast error grows; the simple forecasts sit at the noisy end")
ax.set_ylim(0, 105)
ax.grid(alpha=0.3)
ax.legend(loc="upper right", fontsize=9)
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier2_forecast_value.png"), dpi=150)
plt.close(fig)

# ---- results CSV ----
rows = [
    {"case": "perfect_foresight", "profit_gbp": round(pf, 1), "pct_of_perfect": round(100.0, 1)},
    {"case": "mpc_perfect_window", "profit_gbp": round(pw, 1), "pct_of_perfect": round(pw / pf * 100, 1)},
    {"case": "mpc_same_hour_avg", "profit_gbp": round(sh, 1), "pct_of_perfect": round(sh / pf * 100, 1)},
    {"case": "mpc_persistence", "profit_gbp": round(ps, 1), "pct_of_perfect": round(ps / pf * 100, 1)},
]
for s, v in zip(sigmas, sweep):
    rows.append({"case": f"mpc_noise_sigma_{s}", "profit_gbp": round(v, 1),
                 "pct_of_perfect": round(v / pf * 100, 1)})
pd.DataFrame(rows).to_csv(os.path.join(RESULTS, "tier2_mpc.csv"), index=False)

print("wrote: results/tier2_mpc.csv, plots/tier2_decomposition.png, plots/tier2_forecast_value.png")
for r in rows:
    print(f"  {r['case']:22} GBP {r['profit_gbp']:9,.0f}  {r['pct_of_perfect']:5.1f}%")
