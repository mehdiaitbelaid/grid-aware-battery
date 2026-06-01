"""
Single-area multi-unit load frequency control model.

Several generators share one system frequency (single bus). System inertia is the
capacity-weighted sum of unit inertias; primary (droop) response is the
capacity-weighted sum of governing units' droop gains, plus load damping.

State vector is [df, dPm_0, ..., dPm_{N-1}], all per-unit on the system base:
    df       per-unit frequency deviation
    dPm_i    per-unit mechanical power deviation of generator i

A governor deadband models real governors ignoring tiny frequency error.
This reduces exactly to gridsim.model.SingleAreaLFC when given one aggregate unit
with the deadband switched off. Secondary control (AGC) with ramp limits and
anti-windup is added in a later commit.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .plants import Generator, gb_mix


@dataclass
class PowerSystem:
    """Single-area system of multiple governing/non-governing generators."""

    generators: list[Generator] = field(default_factory=gb_mix)
    D: float = 1.0               # load damping [pu power / pu freq]
    f_nom: float = 50.0          # nominal frequency [Hz]
    s_base_mw: float = 30000.0   # system base power [MW]
    dt: float = 0.01             # integration step [s]
    deadband_hz: float = 0.015   # governor deadband [Hz] (GB primary response ~15 mHz)

    @property
    def H_sys(self) -> float:
        """Capacity-weighted system inertia constant on the system base [s]."""
        return sum(g.H * g.capacity_mw for g in self.generators) / self.s_base_mw

    def droop_gain(self, g: Generator) -> float:
        """System-base droop gain of a generator, (MW_i/MW_base)/R_i, or 0 if it
        does not provide primary response."""
        if not g.governs or g.R <= 0.0:
            return 0.0
        return (g.capacity_mw / self.s_base_mw) / g.R

    @property
    def beta(self) -> float:
        """System frequency response characteristic: sum of droop gains plus damping."""
        return sum(self.droop_gain(g) for g in self.generators) + self.D

    def _deadband(self, df_pu: float) -> float:
        """Governor deadband: ignore errors within the band, subtract it beyond."""
        if self.deadband_hz <= 0.0:
            return df_pu
        db = self.deadband_hz / self.f_nom
        if abs(df_pu) <= db:
            return 0.0
        return df_pu - np.sign(df_pu) * db

    def derivatives(self, y: np.ndarray, dp_pu: float) -> np.ndarray:
        df = y[0]
        pm = y[1:]
        df_droop = self._deadband(df)          # governors see the deadbanded error
        # load damping responds to the full error; only droop sees the deadband
        ddf = (1.0 / (2.0 * self.H_sys)) * (pm.sum() - dp_pu - self.D * df)
        dpm = np.empty(len(self.generators))
        for i, g in enumerate(self.generators):
            dpm[i] = (1.0 / g.Tg) * (-pm[i] - self.droop_gain(g) * df_droop)
        return np.concatenate(([ddf], dpm))

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
        """Simulate a sustained generation loss. Returns (time [s], frequency [Hz])."""
        dp_pu = loss_mw / self.s_base_mw
        n = int(duration / self.dt)
        t = np.linspace(0.0, duration, n)
        y = np.zeros(1 + len(self.generators))
        f = np.empty(n)
        for k, tk in enumerate(t):
            d = dp_pu if tk > trip_time else 0.0
            y = self.rk4_step(y, d)
            f[k] = self.to_hz(y[0])
        return t, f

    def steady_state_offset_hz(self, loss_mw: float) -> float:
        """Analytic droop offset (Hz) ignoring the deadband: -loss_pu / beta, in Hz."""
        dp_pu = loss_mw / self.s_base_mw
        return self.f_nom * (-dp_pu / self.beta)
