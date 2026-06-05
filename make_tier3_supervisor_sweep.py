# Supervisor threshold sweep: the reserve frontier is one slice; the supervisor's own thresholds
# are a second design axis. Sweep the response threshold and measure nadir, trigger delay, and
# chatter (mode transitions) on the severe trip.
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from gridsim.agc import flexible_fast_agc
from gridsim.fleet import FleetResponse
from gridsim.system import PowerSystem
from coupling import RESPONSE, Supervisor, run_coupled

ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(ROOT, "results")
PLOTS = os.path.join(ROOT, "plots")
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(PLOTS, exist_ok=True)

TRIP, DURATION, LOSS, ARB = 20.0, 80.0, 1800.0, -150.0
THRESHOLDS = [49.70, 49.75, 49.80, 49.85]      # response_hz; must stay below the 49.90 reserve line

rows = []
for thr in THRESHOLDS:
    system = PowerSystem(agc=flexible_fast_agc())
    sup = Supervisor(response_hz=thr)
    fleet = FleetResponse(p_fleet_mw=500.0, e_fleet_mwh=1000.0)
    t, f, modes, p, soc = run_coupled(system, sup, fleet, arb_setpoint_mw=ARB,
                                      loss_mw=LOSS, trip_time=TRIP, duration=DURATION)
    transitions = int(sum(1 for i in range(1, len(modes)) if modes[i] != modes[i - 1]))
    resp_idx = [i for i, m in enumerate(modes) if m == RESPONSE]
    trigger_s = float(t[resp_idx[0]] - TRIP) if resp_idx else float("nan")
    rows.append({"response_hz": thr,
                 "nadir_hz": round(float(f.min()), 3),
                 "trigger_s": round(trigger_s, 2),
                 "peak_mw": round(float(p.max()), 0),
                 "transitions": transitions})
    print(f"response {thr:.2f} Hz -> nadir {f.min():.3f} Hz, trigger {trigger_s:+.2f} s, "
          f"peak {p.max():.0f} MW, {transitions} transitions", flush=True)

df = pd.DataFrame(rows)
df.to_csv(os.path.join(RESULTS, "tier3_supervisor_sweep.csv"), index=False)

fig, ax1 = plt.subplots(figsize=(9, 5.2))
ax2 = ax1.twinx()
ax1.plot(df.response_hz, df.nadir_hz, "o-", color="#1f6feb", lw=1.9, label="nadir (Hz)")
ax2.plot(df.response_hz, df.peak_mw, "s--", color="#d29922", lw=1.9, label="peak response (MW)")
ax1.set_xlabel("Supervisor response threshold (Hz)")
ax1.set_ylabel("Nadir (Hz)", color="#1f6feb")
ax2.set_ylabel("Peak response (MW)", color="#d29922")
ax1.set_title("Tier 3: supervisor threshold sweep (1800 MW trip)\n"
              "below the natural dip the reserve never deploys; above it a higher threshold deploys sooner, no chatter")
lines = ax1.get_lines() + ax2.get_lines()
ax1.legend(lines, [ln.get_label() for ln in lines], loc="center right", fontsize=9)
ax1.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier3_supervisor_sweep.png"), dpi=150)
plt.close(fig)

print("\n" + df.to_string(index=False))
print(f"max transitions across the sweep: {df.transitions.max()} (<= 8 means no chatter)")
