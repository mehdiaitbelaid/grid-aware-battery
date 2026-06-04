"""Tier 3 Stage 2 tests: the battery fleet helps the frequency response and is a no-op when off."""
import numpy as np

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
    """With fleet=None the model must reproduce the Tier 1 result exactly."""
    _, f_none = _run(None)
    _, f_base = PowerSystem(agc=flexible_fast_agc()).simulate(
        duration=60.0, trip_time=TRIP, loss_mw=LOSS)
    assert np.allclose(f_none, f_base)


def test_fleet_improves_nadir_and_rocof():
    """A 500 MW fleet must raise the nadir and make the RoCoF less steep."""
    t0, f0 = _run(None)
    t1, f1 = _run(FleetResponse(p_fleet_mw=500.0, e_fleet_mwh=1000.0))
    assert f1.min() > f0.min()                       # higher (better) nadir
    assert _rocof(t1, f1) > _rocof(t0, f0)           # less negative (shallower) RoCoF


def test_bigger_fleet_lifts_nadir_more():
    """More fleet power should lift the nadir further."""
    _, f500 = _run(FleetResponse(p_fleet_mw=500.0, e_fleet_mwh=1000.0))
    _, f2000 = _run(FleetResponse(p_fleet_mw=2000.0, e_fleet_mwh=4000.0))
    assert f2000.min() > f500.min()
