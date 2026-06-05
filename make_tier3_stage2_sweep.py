import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from gridsim.agc import flexible_fast_agc
from gridsim.fleet import FleetResponse
from gridsim.system import PowerSystem
from scenarios.gen_trip import recovery_time, rocof_peak, rocof_window

ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(ROOT, "results")
PLOTS = os.path.join(ROOT, "plots")
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(PLOTS, exist_ok=True)

TRIP = 5.0
DURATION = 120.0


def metrics(t, f):
    rec = recovery_time(t, f, trip_time=TRIP)
    return {"nadir_hz": round(float(f.min()), 3),
            "rocof_500ms_hz_s": round(rocof_window(t, f, TRIP), 3),
            "rocof_peak_hz_s": round(rocof_peak(t, f, TRIP), 3),
            "recovery_s": (round(rec, 1) if np.isfinite(rec) else None),
            "settle_hz": round(float(f[-1]), 4)}


def run(loss_mw, p_fleet_mw):
    fleet = None if p_fleet_mw == 0 else FleetResponse(p_fleet_mw=p_fleet_mw,
                                                       e_fleet_mwh=2.0 * p_fleet_mw)
    ps = PowerSystem(agc=flexible_fast_agc(), fleet=fleet)
    t, f = ps.simulate(duration=DURATION, trip_time=TRIP, loss_mw=loss_mw)
    return t, f, metrics(t, f)


# Part A: fleet-size sweep on the 1320 MW trip
FLEETS = [0, 250, 500, 1000, 1500, 2000]
rowsA = []
for p in FLEETS:
    _, _, m = run(1320.0, p)
    rowsA.append({"fleet_mw": p, **m})
dfA = pd.DataFrame(rowsA)
dfA.to_csv(os.path.join(RESULTS, "tier3_stage2_sweep.csv"), index=False)

fig, ax1 = plt.subplots(figsize=(9, 5.2))
ax2 = ax1.twinx()
ax1.plot(dfA.fleet_mw, dfA.nadir_hz, "o-", color="#1f6feb", lw=1.9, label="nadir (Hz)")
ax2.plot(dfA.fleet_mw, dfA.rocof_500ms_hz_s, "s--", color="#d29922", lw=1.9, label="RoCoF 500 ms avg (Hz/s)")
ax1.set_xlabel("Fleet size (MW)")
ax1.set_ylabel("Nadir (Hz)", color="#1f6feb")
ax2.set_ylabel("RoCoF (Hz/s)", color="#d29922")
ax1.set_title("Tier 3 Stage 2: nadir and RoCoF vs fleet size (1320 MW trip)")
lines = ax1.get_lines() + ax2.get_lines()
ax1.legend(lines, [ln.get_label() for ln in lines], loc="center right", fontsize=9)
ax1.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier3_stage2_sweep.png"), dpi=150)
plt.close(fig)

# Part B: severe 1800 MW trip at several fleet sizes
SEVERE = [0, 500, 1000, 2000]
rowsB, curvesB = [], {}
for p in SEVERE:
    t, f, m = run(1800.0, p)
    curvesB[p] = (t, f)
    m["fleet_mw"] = p
    m["meets_30s"] = bool(m["recovery_s"] is not None and m["recovery_s"] <= 30.0)
    m["above_49p2"] = bool(f.min() >= 49.2)
    rowsB.append(m)
dfB = pd.DataFrame(rowsB)[["fleet_mw", "nadir_hz", "rocof_500ms_hz_s", "rocof_peak_hz_s",
                           "recovery_s", "settle_hz", "meets_30s", "above_49p2"]]
dfB.to_csv(os.path.join(RESULTS, "tier3_stage2_severe.csv"), index=False)

fig, ax = plt.subplots(figsize=(9, 5.2))
ax.axhline(50.0, ls="--", color="black", lw=0.8)
ax.axhline(49.2, ls=":", color="red", lw=1.1, alpha=0.7, label="49.2 Hz floor")
ax.axvline(30.0, ls=":", color="purple", lw=1.0, alpha=0.5, label="30 s target")
for p in SEVERE:
    t, f = curvesB[p]
    lab = "no battery" if p == 0 else f"{p} MW fleet"
    ax.plot(t - TRIP, f, lw=1.7, label=f"{lab} (nadir {f.min():.3f} Hz)")
ax.set_xlim(-3, 60)
ax.set_xlabel("Time since trip (s)")
ax.set_ylabel("Frequency (Hz)")
ax.set_title("Tier 3 Stage 2: 1800 MW trip at several fleet sizes\n"
             "49.2 Hz floor and 30 s target marked")
ax.legend(loc="lower right", fontsize=8.5)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier3_stage2_severe.png"), dpi=150)
plt.close(fig)

print("PART A: fleet-size sweep on the 1320 MW trip")
print(dfA.to_string(index=False))
print("\nPART B: severe 1800 MW trip at several fleet sizes")
print(dfB.to_string(index=False))
