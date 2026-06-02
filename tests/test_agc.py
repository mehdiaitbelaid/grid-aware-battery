"""Tests for the AGC secondary controller."""
import numpy as np

from gridsim.agc import flexible_fast_agc
from gridsim.system import PowerSystem


def test_participation_sums_to_one():
    agc = flexible_fast_agc()
    assert abs(sum(agc.participation.values()) - 1.0) < 1e-9


def test_no_agc_does_not_restore():
    """Droop only must stay off 50 Hz (the bug Tier 1 fixes)."""
    _, f = PowerSystem(agc=None).simulate(duration=120.0, loss_mw=1320.0)
    assert abs(f[-1] - 50.0) > 0.05


def test_agc_restores_to_nominal():
    """With AGC, frequency must return to within +/-0.01 Hz of 50 (given time)."""
    ps = PowerSystem(agc=flexible_fast_agc(t_agc=10.0))
    _, f = ps.simulate(duration=180.0, loss_mw=1320.0)
    assert abs(f[-1] - 50.0) < 0.01


def test_agc_delivers_lost_power_by_participation():
    """At steady state the AGC must supply the lost power, split by participation."""
    loss_mw = 1320.0
    ps = PowerSystem(agc=flexible_fast_agc(t_agc=10.0))
    _, _, Y = ps.simulate(duration=180.0, loss_mw=loss_mw, return_states=True)
    n = len(ps.generators)
    a_final = Y[-1, 2 + n:2 + 2 * n]          # per-unit secondary dispatch
    loss_pu = loss_mw / ps.s_base_mw
    assert abs(a_final.sum() - loss_pu) < 1e-3   # AGC covers the whole loss
    for i, g in enumerate(ps.generators):
        expected = ps.agc.share(g.name) * loss_pu
        assert abs(a_final[i] - expected) < 1e-3  # in the chosen proportions


def test_anti_windup_limits_overshoot():
    """Anti-windup must keep frequency from overshooting 50 by a large margin."""
    ps = PowerSystem(agc=flexible_fast_agc(t_agc=10.0))
    _, f = ps.simulate(duration=180.0, loss_mw=1320.0)
    assert f.max() < 50.05   # small overshoot at most, no runaway above nominal
