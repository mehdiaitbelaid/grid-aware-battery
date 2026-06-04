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

TRIP, DURATION, SURPLUS = 5.0, 120.0, -1320.0   # negative loss = generation surplus / load loss


def zenith_and_rocof(t, f):
    zenith = float(f.max())
    rocof = float(np.gradient(f, t)[(t >= TRIP) & (t <= TRIP + 0.5)].max())
    return zenith, rocof


base = PowerSystem(agc=flexible_fast_agc())
with_fleet = PowerSystem(agc=flexible_fast_agc(), fleet=FleetResponse(p_fleet_mw=500.0, e_fleet_mwh=1000.0))
t, f_base = base.simulate(duration=DURATION, trip_time=TRIP, loss_mw=SURPLUS)
_, f_fleet = with_fleet.simulate(duration=DURATION, trip_time=TRIP, loss_mw=SURPLUS)

zb, rb = zenith_and_rocof(t, f_base)
zf, rf = zenith_and_rocof(t, f_fleet)
rows = [{"case": "AGC only (no battery)", "zenith_hz": round(zb, 3), "rocof_hz_s": round(rb, 3),
         "settle_hz": round(float(f_base[-1]), 4)},
        {"case": "AGC + 500 MW fleet", "zenith_hz": round(zf, 3), "rocof_hz_s": round(rf, 3),
         "settle_hz": round(float(f_fleet[-1]), 4)}]
pd.DataFrame(rows).to_csv(os.path.join(RESULTS, "tier3_overfreq.csv"), index=False)

fig, ax = plt.subplots(figsize=(9, 5.2))
ax.axhspan(49.99, 50.01, color="green", alpha=0.07, label="target band")
ax.axhline(50.5, ls=":", color="red", lw=1.0, alpha=0.6, label="50.5 Hz ceiling")
ax.axhline(50.0, ls="--", color="black", lw=0.8)
ax.plot(t - TRIP, f_base, lw=1.8, color="#888888", label=f"no battery (zenith {zb:.3f} Hz)")
ax.plot(t - TRIP, f_fleet, lw=1.9, color="#1f6feb", label=f"500 MW fleet (zenith {zf:.3f} Hz)")
ax.set_xlim(-3, 40)
ax.set_xlabel("Time since event (s)")
ax.set_ylabel("Frequency (Hz)")
ax.set_title("Over-frequency: 1320 MW generation surplus\n"
             "the symmetric fleet absorbs and contains the rise, the mirror of the nadir case")
ax.legend(loc="upper right", fontsize=8.5)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier3_overfreq.png"), dpi=150)
plt.close(fig)

print(pd.DataFrame(rows).to_string(index=False))
print(f"\nzenith {zb:.3f} -> {zf:.3f} Hz with the fleet; symmetric to the under-frequency nadir case")
