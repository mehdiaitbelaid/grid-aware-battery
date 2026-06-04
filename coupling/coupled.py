from __future__ import annotations

import numpy as np

from gridsim.fleet import FleetResponse
from gridsim.system import PowerSystem

from .supervisor import ARBITRAGE, RECOVERY, RESERVE, RESPONSE, Supervisor


def run_coupled(system: PowerSystem, supervisor: Supervisor, fleet: FleetResponse,
                arb_setpoint_mw: float = -200.0, loss_mw: float = 1800.0,
                trip_time: float = 20.0, duration: float = 80.0):
    n = int(duration / system.dt)
    t = np.linspace(0.0, duration, n)
    y = np.zeros(system.state_size())
    f = np.empty(n)
    modes = np.empty(n, dtype=object)
    p_batt = np.empty(n)

    for k, tk in enumerate(t):
        f_hz = system.to_hz(y[0])
        mode = supervisor.update(f_hz)
        resp_mw = fleet.injection_pu(f_hz, system.f_nom, system.s_base_mw) * system.s_base_mw

        if mode == ARBITRAGE:
            p = arb_setpoint_mw    # TODO: constant stand-in for the hourly MPC dispatch
        elif mode == RESERVE:
            p = max(0.0, arb_setpoint_mw)              # cancel charging and hold ready
        elif mode == RESPONSE:
            p = resp_mw
        else:                                          # RECOVERY
            p = supervisor.taper(f_hz) * resp_mw

        f[k], modes[k], p_batt[k] = f_hz, mode, p
        # only the battery's deviation from its scheduled setpoint moves frequency
        deviation = p - arb_setpoint_mw
        dp_eff = (loss_mw if tk > trip_time else 0.0) - deviation
        y = system.rk4_step(y, dp_eff / system.s_base_mw)

    return t, f, modes, p_batt
