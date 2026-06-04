import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from gridsim.agc import flexible_fast_agc
from gridsim.fleet import FleetResponse
from gridsim.system import PowerSystem
from coupling import ARBITRAGE, RECOVERY, RESERVE, RESPONSE, Supervisor, run_coupled

ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(ROOT, "results")
PLOTS = os.path.join(ROOT, "plots")
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(PLOTS, exist_ok=True)

TRIP, DURATION, LOSS, ARB = 20.0, 80.0, 1800.0, -150.0

system = PowerSystem(agc=flexible_fast_agc())
supervisor = Supervisor()
fleet = FleetResponse(p_fleet_mw=500.0, e_fleet_mwh=1000.0)

t, f, modes, p_batt = run_coupled(system, supervisor, fleet, arb_setpoint_mw=ARB,
                                  loss_mw=LOSS, trip_time=TRIP, duration=DURATION)
tt = t - TRIP

pd.DataFrame({"time_s": t, "freq_hz": f, "mode": modes, "battery_mw": p_batt}).to_csv(
    os.path.join(RESULTS, "tier3_stage3_timeline.csv"), index=False)

# mode transitions and headline numbers
transitions = [(modes[0], 0.0)]
for i in range(1, len(modes)):
    if modes[i] != modes[i - 1]:
        transitions.append((modes[i], round(t[i] - TRIP, 2)))
nadir = float(f.min())
peak_response = float(p_batt.max())

COLORS = {ARBITRAGE: "#cdeccd", RESERVE: "#fbe8a6", RESPONSE: "#f6c3c3", RECOVERY: "#c7d8f5"}


def shade(ax):
    start = 0
    for i in range(1, len(modes) + 1):
        if i == len(modes) or modes[i] != modes[start]:
            ax.axvspan(tt[start], tt[min(i, len(tt) - 1)], color=COLORS[modes[start]], lw=0)
            start = i


fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
shade(ax1)
ax1.axhline(50.0, ls="--", color="black", lw=0.8)
ax1.axhline(49.95, ls=":", color="green", lw=0.9)
ax1.axhline(49.8, ls=":", color="red", lw=0.9)
ax1.plot(tt, f, color="black", lw=1.6)
ax1.set_ylabel("Frequency (Hz)")
ax1.set_xlim(-10, 45)
ax1.set_title("Tier 3 Stage 3: the supervisor switching the battery between arbitrage and response\n"
              "1800 MW trip; the battery drops arbitrage, supports the grid, then returns")
handles = [Patch(color=COLORS[m], label=m) for m in (ARBITRAGE, RESERVE, RESPONSE, RECOVERY)]
ax1.legend(handles=handles, loc="lower right", fontsize=8, ncol=2)
ax1.grid(alpha=0.2)

shade(ax2)
ax2.axhline(0.0, color="black", lw=0.6)
ax2.plot(tt, p_batt, color="#1f6feb", lw=1.6)
ax2.set_ylabel("Battery power (MW)\n(+ discharge / - charge)")
ax2.set_xlabel("Time since trip (s)")
ax2.grid(alpha=0.2)
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier3_stage3_timeline.png"), dpi=150)
plt.close(fig)

print("mode transitions (mode, seconds since trip):")
for m, s in transitions:
    print(f"  {m:9s}  at {s:+.2f} s")
print(f"\nnadir: {nadir:.3f} Hz   peak battery response: {peak_response:.0f} MW   "
      f"arbitrage setpoint: {ARB:.0f} MW")
