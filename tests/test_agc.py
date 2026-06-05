import pytest

from scenarios.gen_trip import recovery_time, rocof_peak, rocof_window
from gridsim.agc import AGC, flexible_fast_agc
from gridsim.system import PowerSystem


def test_participation_sums_to_one():
    agc = flexible_fast_agc()
    assert abs(sum(agc.participation.values()) - 1.0) < 1e-9


def test_pi_gains_are_scaled_to_system_beta():
    ps = PowerSystem(agc=flexible_fast_agc(t_agc=8.0, kp_fraction=0.10))
    assert abs(ps.agc.ki(ps.beta) - ps.beta / 8.0) < 1e-12
    assert abs(ps.agc.kp(ps.beta) - 0.10 * ps.beta) < 1e-12


def test_no_agc_does_not_restore():
    _, f = PowerSystem(agc=None).simulate(duration=120.0, loss_mw=1320.0)
    assert abs(f[-1] - 50.0) > 0.05


def test_agc_restores_to_nominal():
    ps = PowerSystem(agc=flexible_fast_agc())
    _, f = ps.simulate(duration=180.0, loss_mw=1320.0)
    assert abs(f[-1] - 50.0) < 0.01


def test_agc_meets_30_second_recovery_target():
    ps = PowerSystem(agc=flexible_fast_agc())
    t, f = ps.simulate(duration=60.0, loss_mw=1320.0)
    assert recovery_time(t, f, trip_time=5.0) <= 30.0


def test_agc_delivers_lost_power_by_participation():
    loss_mw = 1320.0
    ps = PowerSystem(agc=flexible_fast_agc())
    _, _, Y = ps.simulate(duration=180.0, loss_mw=loss_mw, return_states=True)
    n = len(ps.generators)
    a_final = Y[-1, 2 + n:2 + 2 * n]          # per-unit secondary dispatch
    loss_pu = loss_mw / ps.s_base_mw
    assert abs(a_final.sum() - loss_pu) < 1e-3   # AGC covers the whole loss
    for i, g in enumerate(ps.generators):
        expected = ps.agc.share(g.name) * loss_pu
        assert abs(a_final[i] - expected) < 1e-3  # and in the chosen proportions


def test_anti_windup_limits_overshoot():
    ps = PowerSystem(agc=flexible_fast_agc())
    _, f = ps.simulate(duration=180.0, loss_mw=1320.0)
    assert f.max() < 50.05   # small overshoot at most, no runaway above nominal


def test_agc_robust_across_trip_sizes():
    for loss in (500.0, 1000.0, 1320.0):
        t, f = PowerSystem(agc=flexible_fast_agc()).simulate(duration=120.0, loss_mw=loss)
        assert f.min() >= 49.2                              # holds above the floor
        assert abs(f[-1] - 50.0) < 0.01                     # restores to nominal
        assert recovery_time(t, f, trip_time=5.0) <= 30.0   # within the 30 s target
    # Larger 1800 MW loss still restores and holds the floor, though it may miss 30 s
    t, f = PowerSystem(agc=flexible_fast_agc()).simulate(duration=120.0, loss_mw=1800.0)
    assert f.min() >= 49.2
    assert abs(f[-1] - 50.0) < 0.01


def test_agc_normalises_arbitrary_participation():
    agc = AGC(participation={"A": 2.0, "B": 1.0, "C": 1.0})   # sums to 4, not 1
    assert abs(sum(agc.participation.values()) - 1.0) < 1e-12
    assert abs(agc.share("A") - 0.5) < 1e-12                  # 2 of 4


def test_agc_rejects_invalid_participation():
    with pytest.raises(ValueError):
        AGC(participation={"A": 0.0, "B": 0.0})               # sums to zero
    with pytest.raises(ValueError):
        AGC(participation={"A": -0.5, "B": 1.5})              # a negative share


def test_agc_restores_after_over_frequency():
    # a generation surplus (negative loss) pushes frequency up; the AGC must bring it back down
    ps = PowerSystem(agc=flexible_fast_agc())
    _, f = ps.simulate(duration=180.0, trip_time=5.0, loss_mw=-1320.0)
    assert f.max() > 50.0                                     # it really went over
    assert abs(f[-1] - 50.0) < 0.01                           # AGC restores to nominal
    assert f.min() > 49.95                                    # anti-windup: no big undershoot on the way back


def test_rocof_window_and_peak_match_known_values():
    t, f = PowerSystem(agc=flexible_fast_agc()).simulate(duration=30.0, trip_time=5.0, loss_mw=1320.0)
    assert abs(rocof_window(t, f, 5.0) - (-0.271)) < 0.01     # grid-code 500 ms average
    assert abs(rocof_peak(t, f, 5.0) - (-0.318)) < 0.01       # steepest instantaneous
