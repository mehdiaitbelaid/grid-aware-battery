"""
Single-area load frequency control (LFC) model.

Reimplemented from the author's BEng dissertation RK4 simulator as an importable,
testable module. Two states are tracked:

    df    frequency deviation from nominal
    dpm   deviation of mechanical (turbine) power from its baseline

using the linearised swing equation and a first-order turbine-governor with droop,
integrated by classical fourth-order Runge-Kutta.

This is the Tier 1 baseline (primary/droop control only). Later commits add
per-unit and Hz scaling, a multi-unit generation mix, ramp limits, and secondary
control (AGC).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SingleAreaLFC:
    """Linearised single-area load frequency control model with droop only."""

    H: float = 3.0        # inertia constant [s]
    D: float = 1.0        # load damping [pu power / pu freq]
    R: float = 0.05       # governor droop [pu freq / pu power] (5%)
    Tg: float = 0.3       # lumped governor + turbine time constant [s]
    f_nom: float = 50.0   # nominal frequency [Hz]
    dt: float = 0.01      # integration time step [s]

    def derivatives(self, y: np.ndarray, p_load: float) -> np.ndarray:
        """Time derivatives of [df, dpm] for an imbalance p_load (pu).

        Swing equation:     d(df)/dt  = (1/2H) (dpm - p_load - D df)
        Turbine-governor:   d(dpm)/dt = (1/Tg) (-dpm - (1/R) df)
        """
        df, dpm = y
        ddf = (1.0 / (2.0 * self.H)) * (dpm - p_load - self.D * df)
        ddpm = (1.0 / self.Tg) * (-dpm - (1.0 / self.R) * df)
        return np.array([ddf, ddpm])

    def rk4_step(self, y: np.ndarray, p_load: float) -> np.ndarray:
        """Advance the state one dt using classical fourth-order Runge-Kutta."""
        k1 = self.derivatives(y, p_load)
        k2 = self.derivatives(y + 0.5 * self.dt * k1, p_load)
        k3 = self.derivatives(y + 0.5 * self.dt * k2, p_load)
        k4 = self.derivatives(y + self.dt * k3, p_load)
        return y + (self.dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

    def simulate(self, duration: float = 40.0, step_time: float = 5.0,
                 step_size: float = 0.1):
        """Run a step-disturbance simulation.

        A sustained imbalance of `step_size` (pu) is applied at t = `step_time`.
        Returns (time array [s], frequency array [Hz]).
        """
        n = int(duration / self.dt)
        t = np.linspace(0.0, duration, n)
        y = np.zeros(2)
        f = np.empty(n)
        for i, ti in enumerate(t):
            p_load = step_size if ti > step_time else 0.0
            y = self.rk4_step(y, p_load)
            f[i] = self.f_nom + y[0]
        return t, f
