# Tier 3 co-optimized reserve: the DC reserve is a per-EFA-block decision in the same LP as
# arbitrage, instead of a flat 500 kW. Prints a perfect-foresight and a realistic table and saves
# plots/tier3_coopt.png. weekday_hour_average is the forecaster for the realistic runs.
import os
import warnings

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from battery import BatteryParams, load_prices, solve_arbitrage, run_mpc
from battery.forecast import weekday_hour_average
from battery.coopt import solve_coopt, run_coopt_mpc

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "caseB_grid_battery_market_hourly.csv")
PLOTS = os.path.join(ROOT, "plots")
os.makedirs(PLOTS, exist_ok=True)

EFA_BLOCK = 4
RESERVE_KW = 500.0
DUR_H = 0.5

df, p_da = load_prices(DATA)
avail = df["ancillary_availability_gbp_per_mw_per_h"].to_numpy()
par = BatteryParams()

dc_fixed = 0.5 * float(np.sum(avail))                         # flat 500 kW = 0.5 MW held every hour


def _forecast(p, h, hzn):
    return weekday_hour_average(p, h, hzn)


# perfect foresight
fixed_arb_perfect = solve_arbitrage(
    p_da, par, e_start=par.e0_kwh, e_end_min=par.e0_kwh,
    reserve_power_kw=RESERVE_KW,
    reserve_energy_kwh=RESERVE_KW * DUR_H / par.eta_dis)["profit_gbp"]
fixed_perfect = fixed_arb_perfect + dc_fixed

coopt_efa = solve_coopt(p_da, avail, par, block_size=EFA_BLOCK)
coopt_hourly = solve_coopt(p_da, avail, par, block_size=1)

# realistic forecast
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    fixed_real_mpc = run_mpc(p_da, par, horizon=24, forecast_fn=_forecast,
                             reserve_power_kw=RESERVE_KW,
                             reserve_energy_kwh=RESERVE_KW * DUR_H / par.eta_dis)
fixed_real_arb = fixed_real_mpc["profit_gbp"]
fixed_real = fixed_real_arb + dc_fixed

coopt_efa_real = run_coopt_mpc(p_da, avail, par, horizon=24,
                               da_forecast_fn=weekday_hour_average,
                               av_forecast_fn=weekday_hour_average, block_size=EFA_BLOCK)


def _row(name, arb, dc):
    return f"{name:<34s} {arb:>12,.0f} {dc:>12,.0f} {arb + dc:>12,.0f}"


hdr = f"{'':<34s} {'arb (GBP)':>12s} {'DC (GBP)':>12s} {'total (GBP)':>12s}"

print("PERFECT FORESIGHT")
print(hdr)
print(_row("fixed-500 stack", fixed_arb_perfect, dc_fixed))
print(_row("co-opt reserve, EFA blocks (4h)", coopt_efa["arb_gbp"], coopt_efa["dc_gbp"]))
print(_row("co-opt reserve, hourly blocks", coopt_hourly["arb_gbp"], coopt_hourly["dc_gbp"]))
print()
print("REALISTIC FORECAST (weekday_hour_average)")
print(hdr)
print(_row("fixed-500 stack", fixed_real_arb, dc_fixed))
print(_row("co-opt reserve, EFA blocks (4h)", coopt_efa_real["arb_gbp"], coopt_efa_real["dc_gbp"]))
print()
print(f"co-opt EFA mean reserve: perfect {coopt_efa['reserve_kw'].mean():.0f} kW, "
      f"realistic {coopt_efa_real['reserve_kw'].mean():.0f} kW")

# plot
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

hours = np.arange(len(avail))
axp = ax1.twinx()
l1, = ax1.plot(hours, coopt_efa["reserve_kw"], color="#1f6feb", lw=1.0,
               label="co-opt reserve (EFA, perfect)")
l2, = ax1.plot(hours, coopt_efa_real["reserve_kw"], color="#d62728", lw=0.9, alpha=0.8,
               label="co-opt reserve (EFA, realistic)")
l3, = axp.plot(hours, avail, color="#999999", lw=0.6, alpha=0.7, label="DC availability price")
ax1.set_xlabel("hour")
ax1.set_ylabel("reserve held (kW)")
axp.set_ylabel("DC availability price (GBP/MW/h)")
ax1.set_title("Reserve held vs DC availability price")
ax1.set_ylim(0, par.p_max_kw * 1.05)
ax1.legend(handles=[l1, l2, l3], loc="upper right", fontsize=8)
ax1.grid(alpha=0.3)

labels = ["fixed-500\nperfect", "co-opt EFA\nperfect", "co-opt hourly\nperfect",
          "fixed-500\nrealistic", "co-opt EFA\nrealistic"]
arbs = [fixed_arb_perfect, coopt_efa["arb_gbp"], coopt_hourly["arb_gbp"],
        fixed_real_arb, coopt_efa_real["arb_gbp"]]
dcs = [dc_fixed, coopt_efa["dc_gbp"], coopt_hourly["dc_gbp"], dc_fixed, coopt_efa_real["dc_gbp"]]
x = np.arange(len(labels))
ax2.bar(x, arbs, color="#1f6feb", label="arbitrage")
ax2.bar(x, dcs, bottom=arbs, color="#2ca02c", label="DC availability")
for xi, (a, d) in enumerate(zip(arbs, dcs)):
    ax2.text(xi, a + d + 200, f"{a + d:,.0f}", ha="center", fontsize=8)
ax2.set_xticks(x)
ax2.set_xticklabels(labels, fontsize=8)
ax2.set_ylabel("value over 60 days (GBP)")
ax2.set_title("Value over 60 days: fixed vs co-optimized reserve")
ax2.legend(loc="upper right", fontsize=8.5)
ax2.grid(axis="y", alpha=0.3)

fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier3_coopt.png"), dpi=150)
plt.close(fig)
print(f"\nsaved {os.path.join(PLOTS, 'tier3_coopt.png')}")
