from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SingleAreaLFC:
    H: float = 5.0            # system inertia constant [s], on the system base
    D: float = 1.0            # load damping [pu power / pu freq]
    R: float = 0.05           # governor droop [pu freq / pu power] (5%)
    Tg: float = 0.3           # lumped governor + turbine time constant [s]
    f_nom: float = 50.0       # nominal frequency [Hz]
    s_base_mw: float = 30000.0  # system base power [MW]
    dt: float = 0.01          # integration time step [s]

    def derivatives(self, y: np.ndarray, dp_pu: float) -> np.ndarray:
        # dp_pu > 0 is a generation deficit
        # d(df)/dt = (1/2H) (dpm - dp_pu - D df)
        # d(dpm)/dt = (1/Tg) (-dpm - (1/R) df)
        df, dpm = y
        ddf = (1.0 / (2.0 * self.H)) * (dpm - dp_pu - self.D * df)
        ddpm = (1.0 / self.Tg) * (-dpm - (1.0 / self.R) * df)
        return np.array([ddf, ddpm])

    def rk4_step(self, y: np.ndarray, dp_pu: float) -> np.ndarray:
        k1 = self.derivatives(y, dp_pu)
        k2 = self.derivatives(y + 0.5 * self.dt * k1, dp_pu)
        k3 = self.derivatives(y + 0.5 * self.dt * k2, dp_pu)
        k4 = self.derivatives(y + self.dt * k3, dp_pu)
        return y + (self.dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

    def to_hz(self, df_pu: float) -> float:
        return self.f_nom * (1.0 + df_pu)

    def simulate(self, duration: float = 60.0, trip_time: float = 5.0,
                 loss_mw: float = 1320.0):
        dp_pu = loss_mw / self.s_base_mw
        n = int(duration / self.dt)
        t = np.linspace(0.0, duration, n)
        y = np.zeros(2)
        f = np.empty(n)
        for i, ti in enumerate(t):
            d = dp_pu if ti > trip_time else 0.0
            y = self.rk4_step(y, d)
            f[i] = self.to_hz(y[0])
        return t, f


def steady_state_offset_hz(loss_mw: float, s_base_mw: float = 30000.0,
                           R: float = 0.05, D: float = 1.0,
                           f_nom: float = 50.0) -> float:
    dp_pu = loss_mw / s_base_mw
    df_pu = -dp_pu / (1.0 / R + D)
    return f_nom * df_pu
