"""
Generator-trip scenario: baseline (droop only) versus fixed AGC.

Drops `loss_mw` of generation at `trip_time` and compares the frequency response
with and without secondary control, returning a tidy time series and summary metrics
for the before/after CSV and the recovery plot.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from gridsim.agc import flexible_fast_agc
from gridsim.system import PowerSystem


def recovery_time(t: np.ndarray, f: np.ndarray, trip_time: float,
                  tol: float = 0.01) -> float:
    """Seconds after the trip until frequency stays within +/- tol of 50 Hz."""
    bad = np.where((t >= trip_time) & (np.abs(f - 50.0) >= tol))[0]
    if len(bad) == 0:
        return 0.0
    return float("inf") if bad[-1] + 1 >= len(t) else t[bad[-1] + 1] - trip_time


def run_gen_trip(loss_mw: float = 1320.0, duration: float = 60.0,
                 trip_time: float = 5.0, t_agc: float = 8.0):
    """Run the baseline and AGC responses to a generation trip.

    Returns (DataFrame[time_s, freq_baseline_hz, freq_agc_hz], metrics dict).
    """
    baseline = PowerSystem(agc=None)
    fixed = PowerSystem(agc=flexible_fast_agc(t_agc=t_agc))

    t, f_base = baseline.simulate(duration=duration, trip_time=trip_time, loss_mw=loss_mw)
    _, f_agc = fixed.simulate(duration=duration, trip_time=trip_time, loss_mw=loss_mw)

    df = pd.DataFrame({
        "time_s": t,
        "freq_baseline_hz": f_base,
        "freq_agc_hz": f_agc,
    })

    metrics = {
        "loss_mw": loss_mw,
        "H_sys_s": fixed.H_sys,
        "beta": fixed.beta,
        "Ki": fixed.agc.ki(fixed.beta),
        "Kp": fixed.agc.kp(fixed.beta),
        "kp_fraction": fixed.agc.kp_fraction,
        "t_agc_s": t_agc,
        "baseline_nadir_hz": float(f_base.min()),
        "baseline_settle_hz": float(f_base[-1]),
        "agc_nadir_hz": float(f_agc.min()),
        "agc_settle_hz": float(f_agc[-1]),
        "agc_recovery_s": recovery_time(t, f_agc, trip_time),
        "agc_meets_target": bool(recovery_time(t, f_agc, trip_time) <= 30.0),
    }
    return df, metrics
