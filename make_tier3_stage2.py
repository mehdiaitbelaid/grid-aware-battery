import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from gridsim.agc import flexible_fast_agc
from gridsim.fleet import FleetResponse
from gridsim.system import PowerSystem
from scenarios.gen_trip import recovery_time

ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(ROOT, "results")
PLOTS = os.path.join(ROOT, "plots")
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(PLOTS, exist_ok=True)

TRIP = 5.0
LOSS = 1320.0
DURATION = 60.0


def metrics(t, f):
    rocof = float(np.gradient(f, t)[(t >= TRIP) & (t <= TRIP + 0.5)].min())
    rec = recovery_time(t, f, trip_time=TRIP)
    return {"nadir_hz": round(float(f.min()), 3),
            "rocof_hz_s": round(rocof, 3),
            "recovery_s": round(rec, 1) if np.isfinite(rec) else None,
            "settle_hz": round(float(f[-1]), 4)}


fleet = FleetResponse(p_fleet_mw=500.0, e_fleet_mwh=1000.0)

base = PowerSystem(agc=flexible_fast_agc())                       # AGC, no battery
with_fleet = PowerSystem(agc=flexible_fast_agc(), fleet=fleet)    # AGC + battery fleet

t, f_base = base.simulate(duration=DURATION, trip_time=TRIP, loss_mw=LOSS)
_, f_fleet = with_fleet.simulate(duration=DURATION, trip_time=TRIP, loss_mw=LOSS)

mb, mf = metrics(t, f_base), metrics(t, f_fleet)
rows = [{"case": "AGC only (no battery)", **mb},
        {"case": f"AGC + {int(fleet.p_fleet_mw)} MW fleet", **mf}]
df = pd.DataFrame(rows)[["case", "nadir_hz", "rocof_hz_s", "recovery_s", "settle_hz"]]
df.to_csv(os.path.join(RESULTS, "tier3_stage2.csv"), index=False)

fig, ax = plt.subplots(figsize=(9, 5.2))
ax.axhspan(49.99, 50.01, color="green", alpha=0.07, label="target band")
ax.axhline(49.2, ls=":", color="red", lw=1.0, alpha=0.6, label="49.2 Hz floor")
ax.plot(t - TRIP, f_base, lw=1.8, color="#888888", label=f"no battery (nadir {mb['nadir_hz']} Hz)")
ax.plot(t - TRIP, f_fleet, lw=1.9, color="#1f6feb",
        label=f"{int(fleet.p_fleet_mw)} MW fleet (nadir {mf['nadir_hz']} Hz)")
ax.set_xlim(-3, 40)
ax.set_xlabel("Time since trip (s)")
ax.set_ylabel("Frequency (Hz)")
ax.set_title(f"Tier 3 Stage 2: {int(fleet.p_fleet_mw)} MW fleet on a {int(LOSS)} MW trip\n"
             f"nadir {mb['nadir_hz']} to {mf['nadir_hz']} Hz, "
             f"RoCoF {mb['rocof_hz_s']} to {mf['rocof_hz_s']} Hz/s")
ax.legend(loc="lower right", fontsize=8.5)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier3_stage2_response.png"), dpi=150)
plt.close(fig)

print(df.to_string(index=False))
print(f"\nnadir: {mb['nadir_hz']} to {mf['nadir_hz']} Hz "
      f"({(mf['nadir_hz'] - mb['nadir_hz']) * 1000:+.0f} mHz)")
print(f"RoCoF: {mb['rocof_hz_s']} to {mf['rocof_hz_s']} Hz/s "
      f"({(mf['rocof_hz_s'] - mb['rocof_hz_s']):+.3f} Hz/s, less steep is better)")
