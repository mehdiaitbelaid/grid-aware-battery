"""Generate the Tier 1 deliverables: the before/after CSV and the recovery plot."""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from scenarios.gen_trip import run_gen_trip

ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(ROOT, "results")
PLOTS = os.path.join(ROOT, "plots")
os.makedirs(RESULTS, exist_ok=True)
os.makedirs(PLOTS, exist_ok=True)

TRIP = 5.0
df, m = run_gen_trip(loss_mw=1320.0, duration=60.0, trip_time=TRIP, t_agc=8.0)

csv_path = os.path.join(RESULTS, "tier1_gen_trip.csv")
df.to_csv(csv_path, index=False)

# time measured from the trip, so the axis reads what the labels say
x = df.time_s - TRIP

fig, ax = plt.subplots(figsize=(10, 5.6))
ax.axhspan(49.99, 50.01, color="green", alpha=0.08, label="target band (+/-0.01 Hz)")
ax.axhline(50.0, ls="--", color="black", lw=1.2, label="50.000 Hz")
ax.plot(x, df.freq_baseline_hz, color="grey", lw=1.7,
        label=f"baseline, droop only (parks {m['baseline_settle_hz']:.3f} Hz)")
ax.plot(x, df.freq_agc_hz, color="tab:green", lw=2.1, label="with AGC")
ax.axvline(0.0, ls=":", color="gray", lw=1.0, label="trip")
ax.axvline(m["agc_recovery_s"], ls="-", color="tab:green", lw=1.0, alpha=0.5,
           label=f"recovered ({m['agc_recovery_s']:.0f} s)")
ax.axvline(30.0, ls=":", color="purple", lw=1.2, alpha=0.7, label="30 s deadline")
ax.set_xlim(-3, 50)
ax.set_xlabel("Time since trip (s)")
ax.set_ylabel("Frequency (Hz)")
ax.set_title("Tier 1: secondary control (AGC) returns frequency within +/-0.01 Hz after a 1320 MW trip\n"
             f"GB high-wind mix: H_sys = {m['H_sys_s']:.2f} s, Ki = {m['Ki']:.2f}, Kp = {m['Kp']:.2f}")
ax.legend(loc="lower right", fontsize=8.5)
ax.grid(alpha=0.3)
fig.tight_layout()
png_path = os.path.join(PLOTS, "tier1_recovery.png")
fig.savefig(png_path, dpi=150)

print("wrote:", os.path.relpath(csv_path, ROOT))
print("wrote:", os.path.relpath(png_path, ROOT))
print("\nsummary:")
for k, v in m.items():
    print(f"  {k}: {v}")
