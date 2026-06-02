"""
Single-area multi-unit load frequency control model, with optional AGC.

Several generators share one system frequency (single bus). System inertia is the
capacity-weighted sum of unit inertias; primary (droop) response is the
capacity-weighted sum of governing units' droop gains, plus load damping. A governor
deadband models real governors ignoring tiny frequency error.

Without an AGC the state is [df, dPm_0..dPm_{N-1}] (droop only). With an AGC two more
blocks are appended: the integral command P_int and each unit's ramp-limited secondary
dispatch a_0..a_{N-1}, all per-unit on the system base:

    df       per-unit frequency deviation
    dPm_i    per-unit mechanical power deviation of generator i
    P_int    integral part of the secondary power command
    a_i      secondary power actually dispatched to generator i (ramp limited)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .agc import AGC
from .plants import Generator, gb_mix


@dataclass
class PowerSystem:
    """Single-area system of multiple generators, with optional secondary control."""

    generators: list[Generator] = field(default_factory=gb_mix)
    D: float = 1.0               # load damping [pu power / pu freq]
    f_nom: float = 50.0          # nominal frequency [Hz]
    s_base_mw: float = 30000.0   # system base power [MW]
    dt: float = 0.01             # integration step [s]
    deadband_hz: float = 0.015   # governor deadband [Hz] (GB primary response ~15 mHz)
    agc: AGC | None = None       # secondary controller (None = droop only)

    # ---- system aggregates ------------------------------------------------
    @property
    def H_sys(self) -> float:
        """Capacity-weighted system inertia constant on the system base [s]."""
        return sum(g.H * g.capacity_mw for g in self.generators) / self.s_base_mw

    def droop_gain(self, g: Generator) -> float:
        """System-base droop gain of a generator, (MW_i/MW_base)/R_i, or 0."""
        if not g.governs or g.R <= 0.0:
            return 0.0
        return (g.capacity_mw / self.s_base_mw) / g.R

    @property
    def beta(self) -> float:
        """System frequency response characteristic: sum of droop gains plus damping."""
        return sum(self.droop_gain(g) for g in self.generators) + self.D

    def ramp_pu_per_s(self, g: Generator) -> float:
        """Secondary ramp limit of a generator in per-unit (system base) per second."""
        mw_per_s = (g.ramp_pct_per_min / 100.0) * g.capacity_mw / 60.0
        return mw_per_s / self.s_base_mw

    def _deadband(self, df_pu: float) -> float:
        """Governor deadband: ignore errors within the band, subtract it beyond."""
        if self.deadband_hz <= 0.0:
            return df_pu
        db = self.deadband_hz / self.f_nom
        if abs(df_pu) <= db:
            return 0.0
        return df_pu - np.sign(df_pu) * db

    # ---- dynamics ---------------------------------------------------------
    def derivatives(self, y: np.ndarray, dp_pu: float) -> np.ndarray:
        n = len(self.generators)
        df = y[0]
        pm = y[1:1 + n]
        df_droop = self._deadband(df)

        if self.agc is not None:
            p_int = y[1 + n]
            a = y[2 + n:2 + 2 * n]
        else:
            a = np.zeros(n)

        # swing equation (load damping sees the full error)
        ddf = (1.0 / (2.0 * self.H_sys)) * (pm.sum() - dp_pu - self.D * df)

        # each governor tracks droop response plus its AGC setpoint a_i
        dpm = np.empty(n)
        for i, g in enumerate(self.generators):
            dpm[i] = (1.0 / g.Tg) * (-pm[i] - self.droop_gain(g) * df_droop + a[i])

        if self.agc is None:
            return np.concatenate(([ddf], dpm))

        # secondary loop: PI command, with back-calculation anti-windup on the integral
        ki = self.agc.ki(self.beta)
        kp = self.agc.kp(self.beta)
        a_total = a.sum()
        p_secondary = p_int + kp * (-df)
        dp_int = ki * (-df) + (1.0 / self.agc.t_aw) * (a_total - p_secondary)

        # each unit moves toward its share, capped by its ramp limit
        da = np.empty(n)
        for i, g in enumerate(self.generators):
            target = self.agc.share(g.name) * p_secondary
            ramp = self.ramp_pu_per_s(g)
            rate = (target - a[i]) / self.agc.t_actuator
            da[i] = float(np.clip(rate, -ramp, ramp))

        return np.concatenate(([ddf], dpm, [dp_int], da))

    def rk4_step(self, y: np.ndarray, dp_pu: float) -> np.ndarray:
        k1 = self.derivatives(y, dp_pu)
        k2 = self.derivatives(y + 0.5 * self.dt * k1, dp_pu)
        k3 = self.derivatives(y + 0.5 * self.dt * k2, dp_pu)
        k4 = self.derivatives(y + self.dt * k3, dp_pu)
        return y + (self.dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

    def to_hz(self, df_pu: float) -> float:
        return self.f_nom * (1.0 + df_pu)

    def state_size(self) -> int:
        n = len(self.generators)
        return 1 + n + (1 + n if self.agc is not None else 0)

    def simulate(self, duration: float = 60.0, trip_time: float = 5.0,
                 loss_mw: float = 1320.0, return_states: bool = False):
        """Simulate a sustained generation loss.

        Returns (time [s], frequency [Hz]), or (time, frequency, states) if
        `return_states`, where states has shape (steps, state_size).
        """
        dp_pu = loss_mw / self.s_base_mw
        n = int(duration / self.dt)
        t = np.linspace(0.0, duration, n)
        y = np.zeros(self.state_size())
        f = np.empty(n)
        Y = np.empty((n, self.state_size())) if return_states else None
        for k, tk in enumerate(t):
            d = dp_pu if tk > trip_time else 0.0
            y = self.rk4_step(y, d)
            f[k] = self.to_hz(y[0])
            if return_states:
                Y[k] = y
        if return_states:
            return t, f, Y
        return t, f

    def steady_state_offset_hz(self, loss_mw: float) -> float:
        """Analytic droop offset (Hz) ignoring the deadband: -loss_pu / beta, in Hz."""
        dp_pu = loss_mw / self.s_base_mw
        return self.f_nom * (-dp_pu / self.beta)
