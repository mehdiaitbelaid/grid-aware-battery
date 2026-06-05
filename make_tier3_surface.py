import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from gridsim.agc import flexible_fast_agc
from gridsim.fleet import FleetResponse
from gridsim.system import PowerSystem

ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(ROOT, "results")
PLOTS = os.path.join(ROOT, "plots")
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(PLOTS, exist_ok=True)

TRIP, DURATION, LOSS = 5.0, 60.0, 1800.0
RESERVES = [250, 500, 1000, 2000]      # MW of reserved fleet power
RAMPS = [50, 100, 200, 500, 1000]      # MW/s ramp rate of the response


def nadir_for(reserve_mw, ramp_mw_per_s):
    fleet = FleetResponse(p_fleet_mw=float(reserve_mw), e_fleet_mwh=2.0 * reserve_mw)
    system = PowerSystem(agc=flexible_fast_agc())
    n = int(DURATION / system.dt)
    t = np.linspace(0.0, DURATION, n)
    y = np.zeros(system.state_size())
    p, fmin = 0.0, 50.0
    max_step = ramp_mw_per_s * system.dt
    for tk in t:
        f_hz = system.to_hz(y[0])
        fmin = min(fmin, f_hz)
        target = fleet.injection_pu(f_hz, system.f_nom, system.s_base_mw) * system.s_base_mw
        p = min(max(target, p - max_step), p + max_step)
        dp_eff = (LOSS if tk > TRIP else 0.0) - p
        y = system.rk4_step(y, dp_eff / system.s_base_mw)
    return fmin


Z = np.array([[nadir_for(r, rr) for rr in RAMPS] for r in RESERVES])
nobatt = float(PowerSystem(agc=flexible_fast_agc())
               .simulate(duration=DURATION, trip_time=TRIP, loss_mw=LOSS)[1].min())

pd.DataFrame(np.round(Z, 3), index=[f"reserve_{r}MW" for r in RESERVES],
             columns=[f"ramp_{rr}MWs" for rr in RAMPS]).to_csv(
    os.path.join(RESULTS, "tier3_surface.csv"))

fig, ax = plt.subplots(figsize=(8.2, 5.4))
im = ax.imshow(Z, aspect="auto", origin="lower", cmap="RdYlGn")
ax.set_xticks(range(len(RAMPS)))
ax.set_xticklabels(RAMPS)
ax.set_yticks(range(len(RESERVES)))
ax.set_yticklabels(RESERVES)
ax.set_xlabel("Fleet ramp rate (MW/s)")
ax.set_ylabel("Reserved power (MW)")
for i in range(len(RESERVES)):
    for j in range(len(RAMPS)):
        ax.text(j, i, f"{Z[i, j]:.3f}", ha="center", va="center", color="black", fontsize=8.5)
cbar = fig.colorbar(im)
cbar.set_label("Nadir (Hz)")
ax.set_title(f"Tier 3: nadir over reserve and ramp rate (1800 MW trip)\n"
             f"no battery nadir {nobatt:.3f} Hz")
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier3_surface.png"), dpi=150)
plt.close(fig)

print(f"no battery nadir: {nobatt:.3f} Hz")
print("nadir (Hz), rows = reserve MW, cols = ramp MW/s:")
print(pd.DataFrame(np.round(Z, 3), index=RESERVES, columns=RAMPS).to_string())
