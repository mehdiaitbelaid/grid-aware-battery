import numpy as np

from coupling import RESPONSE, Supervisor, run_coupled
from gridsim.agc import flexible_fast_agc
from gridsim.fleet import FleetResponse
from gridsim.system import PowerSystem

TRIP = 5.0
LOSS = 1320.0


def _run(fleet):
    ps = PowerSystem(agc=flexible_fast_agc(), fleet=fleet)
    return ps.simulate(duration=60.0, trip_time=TRIP, loss_mw=LOSS)


def _rocof(t, f):
    return float(np.gradient(f, t)[(t >= TRIP) & (t <= TRIP + 0.5)].min())


def test_fleet_none_is_a_noop():
    _, f_none = _run(None)
    _, f_base = PowerSystem(agc=flexible_fast_agc()).simulate(
        duration=60.0, trip_time=TRIP, loss_mw=LOSS)
    assert np.allclose(f_none, f_base)


def test_fleet_improves_nadir_and_rocof():
    t0, f0 = _run(None)
    t1, f1 = _run(FleetResponse(p_fleet_mw=500.0, e_fleet_mwh=1000.0))
    assert f1.min() > f0.min()                       # higher (better) nadir
    assert _rocof(t1, f1) > _rocof(t0, f0)           # less negative (shallower) RoCoF


def test_bigger_fleet_lifts_nadir_more():
    _, f500 = _run(FleetResponse(p_fleet_mw=500.0, e_fleet_mwh=1000.0))
    _, f2000 = _run(FleetResponse(p_fleet_mw=2000.0, e_fleet_mwh=4000.0))
    assert f2000.min() > f500.min()


def test_fleet_absorbs_in_over_frequency():
    fleet = FleetResponse(p_fleet_mw=500.0, e_fleet_mwh=1000.0)
    low = fleet.injection_pu(49.5, 50.0, 30000.0)    # under-frequency -> discharge (inject)
    high = fleet.injection_pu(50.5, 50.0, 30000.0)   # over-frequency -> charge (absorb)
    assert low > 0 and high < 0
    assert abs(low + high) < 1e-12                   # symmetric magnitude about nominal


def test_coupled_debits_event_energy_and_holds_reserve_floor():
    system = PowerSystem(agc=flexible_fast_agc())
    fleet = FleetResponse(p_fleet_mw=500.0, e_fleet_mwh=1000.0)
    floor = fleet.reserve * 0.5
    _, f, modes, p, soc = run_coupled(system, Supervisor(), fleet, arb_setpoint_mw=-150.0,
                                      loss_mw=1800.0, trip_time=20.0, duration=80.0)
    resp = [i for i, m in enumerate(modes) if m == RESPONSE]
    assert resp                                       # the event really happened
    assert soc[resp[-1]] < soc[resp[0]]               # discharging debits the stored energy
    assert soc.min() >= floor - 1e-6                  # reserve stays deliverable throughout
    # the SoC ledger matches the integral of net battery power, eta counted once
    dt_h, eta = system.dt / 3600.0, 0.9381
    e_start = max(floor, 0.5 * fleet.e_fleet_mwh)               # run_coupled's default start SoC
    drawn = float(np.clip(p, 0.0, None).sum()) * dt_h / eta     # discharge draws extra for losses
    added = float(np.clip(-p, 0.0, None).sum()) * dt_h * eta    # charge stores less
    assert abs(soc[-1] - (e_start + added - drawn)) < 1e-6


def test_reserve_floor_caps_discharge_when_energy_is_low():
    system = PowerSystem(agc=flexible_fast_agc())
    fleet = FleetResponse(p_fleet_mw=500.0, e_fleet_mwh=1000.0)
    floor = fleet.reserve * 0.5
    # start at the floor with no pre-trip charging, so there is no headroom and the cap must block
    # the response (with arb_setpoint=-150 the pre-charge lifted SoC and the cap never fired)
    _, f, modes, p, soc = run_coupled(system, Supervisor(), fleet, arb_setpoint_mw=0.0,
                                      loss_mw=1800.0, trip_time=20.0, duration=80.0,
                                      e_start_mwh=floor, reserve_floor_mwh=floor)
    assert soc.min() >= floor - 1e-9                       # floor never breached
    assert float(np.clip(p, 0.0, None).max()) < 1.0       # no headroom, so the response is throttled to ~0


def test_coupled_inertia_lifts_nadir_slightly():
    # Stage 3 must carry the Stage 2 synthetic inertia (attached inside run_coupled), so the
    # supervised run sits a touch above a hypothetical inertia-free run.
    system = PowerSystem(agc=flexible_fast_agc())
    fleet = FleetResponse(p_fleet_mw=500.0, e_fleet_mwh=1000.0)
    _, f, _, _, _ = run_coupled(system, Supervisor(), fleet, arb_setpoint_mw=-150.0,
                                loss_mw=1800.0, trip_time=20.0, duration=80.0)
    assert system.fleet is None                       # run_coupled restored the system, no mutation
    assert f.min() > 49.77                            # inertia plus supervised droop holds the nadir
