"""Response speed: at a fixed 500 MW reserve, sweep the fleet ramp rate on the 1800 MW trip.
A fast ramp lifts the nadir, a slow one arrives too late. Faster also cycles harder."""
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
fleet = FleetResponse(p_fleet_mw=500.0, e_fleet_mwh=1000.0)


def run_ramp(ramp_mw_per_s):
    # droop response injected through the loss term, rate-limited toward the droop target
    system = PowerSystem(agc=flexible_fast_agc())
    n = int(DURATION / system.dt)
    t = np.linspace(0.0, DURATION, n)
    y = np.zeros(system.state_size())
    f = np.empty(n)
    p = 0.0
    max_step = ramp_mw_per_s * system.dt
    for k, tk in enumerate(t):
        f_hz = system.to_hz(y[0])
        f[k] = f_hz
        target = fleet.injection_pu(f_hz, system.f_nom, system.s_base_mw) * system.s_base_mw
        p = min(max(target, p - max_step), p + max_step)
        dp_eff = (LOSS if tk > TRIP else 0.0) - p
        y = system.rk4_step(y, dp_eff / system.s_base_mw)
    return float(f.min())


ramps = [("instant", 1.0e9), ("1000", 1000.0), ("500", 500.0), ("200", 200.0), ("100", 100.0), ("50", 50.0)]
rows = [{"ramp_mw_per_s": label, "nadir_hz": round(run_ramp(r), 3)} for label, r in ramps]

nadir_none = round(float(PowerSystem(agc=flexible_fast_agc())
                        .simulate(duration=DURATION, trip_time=TRIP, loss_mw=LOSS)[1].min()), 3)

df = pd.DataFrame(rows)
df.to_csv(os.path.join(RESULTS, "tier3_speed.csv"), index=False)

xr = [1000, 500, 200, 100, 50]
yr = [r["nadir_hz"] for r in rows[1:]]
fig, ax = plt.subplots(figsize=(8.5, 5.0))
ax.axhline(nadir_none, ls=":", color="#888888", label=f"no battery ({nadir_none} Hz)")
ax.axhline(rows[0]["nadir_hz"], ls="--", color="#1f6feb", alpha=0.6,
           label=f"instant ramp ({rows[0]['nadir_hz']} Hz)")
ax.plot(xr, yr, "o-", color="#d29922", lw=1.9, label="nadir vs ramp rate")
ax.set_xscale("log")
ax.set_xlabel("Fleet ramp rate (MW/s, log scale)")
ax.set_ylabel("Nadir (Hz)")
ax.set_title("Response speed, the third axis: a faster fleet ramp lifts the nadir more\n"
             "500 MW reserve on the 1800 MW trip; a slow ramp arrives too late to help the dip")
ax.legend(loc="lower right", fontsize=8.5)
ax.grid(alpha=0.3, which="both")
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier3_speed.png"), dpi=150)
plt.close(fig)

print(f"no battery nadir: {nadir_none} Hz")
print(df.to_string(index=False))
