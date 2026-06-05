import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from gridsim.agc import flexible_fast_agc
from gridsim.plants import Generator, gb_mix
from gridsim.system import PowerSystem
from scenarios.gen_trip import recovery_time, rocof_peak, rocof_window

ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(ROOT, "results")
PLOTS = os.path.join(ROOT, "plots")
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(PLOTS, exist_ok=True)
TRIP = 5.0


def metrics(t, f):
    rec = recovery_time(t, f, trip_time=TRIP)
    return {
        "nadir_hz": round(float(f.min()), 3),
        "rocof_500ms_hz_s": round(rocof_window(t, f, TRIP), 3),   # grid-code style window average
        "rocof_peak_hz_s": round(rocof_peak(t, f, TRIP), 3),      # steepest instantaneous (conservative)
        "recovery_s": (round(rec, 1) if np.isfinite(rec) else None),
        "overshoot_mhz": round(max(float(f.max()) - 50.0, 0.0) * 1000, 1),
        "settle_hz": round(float(f[-1]), 4),
    }


# 1. Robustness across trip sizes
losses = [500, 1000, 1320, 1800]
rob, curves = [], {}
for loss in losses:
    t, f = PowerSystem(agc=flexible_fast_agc()).simulate(duration=120.0, loss_mw=loss)
    curves[loss] = (t, f)
    m = metrics(t, f)
    m.update(loss_mw=loss,
             meets_30s=bool(m["recovery_s"] is not None and m["recovery_s"] <= 30.0),
             above_49p2=bool(f.min() >= 49.2),
             within_rocof_limit=bool(abs(m["rocof_peak_hz_s"]) <= 1.0))   # GB limit 1 Hz/s; peak is the conservative test
    rob.append(m)
rob_df = pd.DataFrame(rob)[["loss_mw", "nadir_hz", "rocof_500ms_hz_s", "rocof_peak_hz_s",
                            "within_rocof_limit", "recovery_s", "overshoot_mhz", "settle_hz",
                            "meets_30s", "above_49p2"]]
rob_df.to_csv(os.path.join(RESULTS, "tier1_robustness.csv"), index=False)

fig, ax = plt.subplots(figsize=(9, 5.2))
ax.axhspan(49.99, 50.01, color="green", alpha=0.07, label="target band")
ax.axhline(50.0, ls="--", color="black", lw=1.0)
ax.axvline(30.0, ls=":", color="purple", lw=1.1, alpha=0.6, label="30 s target")
for loss in losses:
    t, f = curves[loss]
    ax.plot(t - TRIP, f, lw=1.8, label=f"{loss} MW")
ax.set_xlim(-3, 60)
ax.set_xlabel("Time since trip (s)")
ax.set_ylabel("Frequency (Hz)")
ax.set_title("Tier 1 robustness: AGC recovery across trip sizes\n"
             "tuned on 1320 MW; restores 50 Hz for all, the 1800 MW case just misses 30 s")
ax.legend(loc="lower right", fontsize=8.5)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "tier1_robustness.png"), dpi=150)
plt.close(fig)

# 2. Gain sweep, basis for T_agc = 8 s and Kp = 0.10 * beta
gain = []
for ta in [6, 8, 10, 12]:
    ps = PowerSystem(agc=flexible_fast_agc(t_agc=ta, kp_fraction=0.10))
    m = metrics(*ps.simulate(duration=90.0, loss_mw=1320.0))
    gain.append({"vary": "T_agc", "value": ta, "Ki": round(ps.agc.ki(ps.beta), 2),
                 "Kp": round(ps.agc.kp(ps.beta), 2),
                 "recovery_s": m["recovery_s"], "overshoot_mhz": m["overshoot_mhz"]})
for kf in [0.0, 0.05, 0.10, 0.20]:
    ps = PowerSystem(agc=flexible_fast_agc(t_agc=8.0, kp_fraction=kf))
    m = metrics(*ps.simulate(duration=90.0, loss_mw=1320.0))
    gain.append({"vary": "kp_fraction", "value": kf, "Ki": round(ps.agc.ki(ps.beta), 2),
                 "Kp": round(ps.agc.kp(ps.beta), 2),
                 "recovery_s": m["recovery_s"], "overshoot_mhz": m["overshoot_mhz"]})
gain_df = pd.DataFrame(gain)
gain_df.to_csv(os.path.join(RESULTS, "tier1_gain_sweep.csv"), index=False)


# 3. Ablation: what each control piece changes
def huge_ramp_mix():
    return [Generator(g.name, g.fuel, g.capacity_mw, g.H, g.R, g.Tg, g.governs,
                      ramp_pct_per_min=1.0e6) for g in gb_mix()]


abl = []
for label, ps in [
    ("droop only (no AGC)", PowerSystem(agc=None)),
    ("AGC, no ramp limits", PowerSystem(generators=huge_ramp_mix(), agc=flexible_fast_agc())),
    ("AGC, with ramp limits", PowerSystem(agc=flexible_fast_agc())),
]:
    m = metrics(*ps.simulate(duration=120.0, loss_mw=1320.0))
    m["case"] = label
    abl.append(m)
abl_df = pd.DataFrame(abl)[["case", "nadir_hz", "recovery_s", "overshoot_mhz", "settle_hz"]]
abl_df.to_csv(os.path.join(RESULTS, "tier1_ablation.csv"), index=False)

# 4. Participation split
part_df = pd.DataFrame([{"unit": k, "participation": v}
                        for k, v in flexible_fast_agc().participation.items()])

print("1) ROBUSTNESS across trip sizes (AGC):")
print(rob_df.to_string(index=False))
print("\n2) GAIN SWEEP (1320 MW design trip):")
print(gain_df.to_string(index=False))
print("\n3) ABLATION (1320 MW trip):")
print(abl_df.to_string(index=False))
print("\n4) PARTICIPATION split (sums to 1):")
print(part_df.to_string(index=False))
print("\nwrote results/tier1_robustness.csv, tier1_gain_sweep.csv, tier1_ablation.csv,"
      " and plots/tier1_robustness.png")
