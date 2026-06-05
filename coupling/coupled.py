from __future__ import annotations

from dataclasses import replace

import numpy as np

from gridsim.fleet import FleetResponse
from gridsim.system import PowerSystem

from .supervisor import ARBITRAGE, RECOVERY, RESERVE, RESPONSE, Supervisor


def run_coupled(system: PowerSystem, supervisor: Supervisor, fleet: FleetResponse,
                arb_setpoint_mw: float = -150.0, loss_mw: float = 1800.0,
                trip_time: float = 20.0, duration: float = 80.0,
                e_start_mwh: float | None = None, reserve_floor_mwh: float | None = None,
                eta: float = 0.9381):
    # Reserve deliverability floor: keep enough stored energy to sustain the reserve for 30 min.
    if reserve_floor_mwh is None:
        reserve_floor_mwh = fleet.reserve * 0.5                 # MW * 0.5 h
    if e_start_mwh is None:
        e_start_mwh = max(reserve_floor_mwh, 0.5 * fleet.e_fleet_mwh)

    n = int(duration / system.dt)
    t = np.linspace(0.0, duration, n)      # uniform grid; spacing within 0.02% of dt, metrics robust to it
    dt_h = system.dt / 3600.0
    y = np.zeros(system.state_size())
    f = np.empty(n)
    modes = np.empty(n, dtype=object)
    p_batt = np.empty(n)
    soc = np.empty(n)

    # Synthetic inertia is a passive property of the connected fleet, so attach an inertia-only
    # copy (reserve_mw=0 zeroes its droop) for the swing equation and let the supervisor own the
    # droop below. This matches the Stage 2 physics without double counting the droop. Restored
    # in finally so run_coupled does not mutate the caller's system.
    saved_fleet = system.fleet
    system.fleet = replace(fleet, reserve_mw=0.0)
    e = float(e_start_mwh)
    try:
        for k, tk in enumerate(t):
            f_hz = system.to_hz(y[0])
            mode = supervisor.update(f_hz)
            resp_mw = fleet.injection_pu(f_hz, system.f_nom, system.s_base_mw) * system.s_base_mw

            if mode == ARBITRAGE:
                p_req = arb_setpoint_mw                 # constant stand-in for the hourly MPC dispatch
            elif mode == RESERVE:
                p_req = max(0.0, arb_setpoint_mw)       # cancel charging and hold ready
            elif mode == RESPONSE:
                p_req = resp_mw
            else:                                       # RECOVERY
                p_req = supervisor.taper(f_hz) * resp_mw

            # the battery can only discharge what its stored energy allows above the reserve floor
            if p_req > 0.0:
                deliverable = max(0.0, e - reserve_floor_mwh) * eta / dt_h
                p = min(p_req, deliverable)
            else:
                p = p_req

            # debit the state of charge with charge/discharge efficiency
            if p >= 0.0:
                e -= (p / eta) * dt_h                   # discharging draws stored energy
            else:
                e += (-p * eta) * dt_h                  # charging adds it
            e = float(min(max(e, 0.0), fleet.e_fleet_mwh))

            f[k], modes[k], p_batt[k], soc[k] = f_hz, mode, p, e
            # only the battery's deviation from its scheduled setpoint moves frequency
            deviation = p - arb_setpoint_mw
            dp_eff = (loss_mw if tk > trip_time else 0.0) - deviation
            y = system.rk4_step(y, dp_eff / system.s_base_mw)
    finally:
        system.fleet = saved_fleet

    return t, f, modes, p_batt, soc
