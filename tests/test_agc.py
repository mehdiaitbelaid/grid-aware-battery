"""Tests for the AGC secondary controller."""
from scenarios.gen_trip import recovery_time
from gridsim.agc import flexible_fast_agc
from gridsim.system import PowerSystem


def test_participation_sums_to_one():
    agc = flexible_fast_agc()
    assert abs(sum(agc.participation.values()) - 1.0) < 1e-9


def test_pi_gains_are_scaled_to_system_beta():
    """PI gains must be derived from beta, not arbitrary fixed constants."""
    ps = PowerSystem(agc=flexible_fast_agc(t_agc=8.0, kp_fraction=0.10))
    assert abs(ps.agc.ki(ps.beta) - ps.beta / 8.0) < 1e-12
    assert abs(ps.agc.kp(ps.beta) - 0.10 * ps.beta) < 1e-12


def test_no_agc_does_not_restore():
    """Droop only must stay off 50 Hz (the bug Tier 1 fixes)."""
    _, f = PowerSystem(agc=None).simulate(duration=120.0, loss_mw=1320.0)
    assert abs(f[-1] - 50.0) > 0.05


def test_agc_restores_to_nominal():
    """With AGC, frequency must return to within +/-0.01 Hz of 50 (given time)."""
    ps = PowerSystem(agc=flexible_fast_agc())
    _, f = ps.simulate(duration=180.0, loss_mw=1320.0)
    assert abs(f[-1] - 50.0) < 0.01


def test_agc_meets_30_second_recovery_target():
    """Tier 1 target: stay within +/-0.01 Hz of nominal within 30 s of the trip."""
    ps = PowerSystem(agc=flexible_fast_agc())
    t, f = ps.simulate(duration=60.0, loss_mw=1320.0)
    assert recovery_time(t, f, trip_time=5.0) <= 30.0


def test_agc_delivers_lost_power_by_participation():
    """At steady state the AGC must supply the lost power, split by participation."""
    loss_mw = 1320.0
    ps = PowerSystem(agc=flexible_fast_agc())
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
    ps = PowerSystem(agc=flexible_fast_agc())
    _, f = ps.simulate(duration=180.0, loss_mw=1320.0)
    assert f.max() < 50.05   # small overshoot at most, no runaway above nominal


def test_agc_robust_across_trip_sizes():
    """The AGC restores 50 Hz and stays above the 49.2 Hz floor across a range of trips;
    the design case and smaller also meet the 30 s target."""
    for loss in (500.0, 1000.0, 1320.0):
        t, f = PowerSystem(agc=flexible_fast_agc()).simulate(duration=120.0, loss_mw=loss)
        assert f.min() >= 49.2                              # holds above the floor
        assert abs(f[-1] - 50.0) < 0.01                     # restores to nominal
        assert recovery_time(t, f, trip_time=5.0) <= 30.0   # within the 30 s target
    # the larger 1800 MW loss still restores and holds the floor (it may miss 30 s)
    t, f = PowerSystem(agc=flexible_fast_agc()).simulate(duration=120.0, loss_mw=1800.0)
    assert f.min() >= 49.2
    assert abs(f[-1] - 50.0) < 0.01
