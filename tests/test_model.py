import numpy as np

from gridsim.model import SingleAreaLFC, steady_state_offset_hz


def test_zero_disturbance_stays_at_nominal():
    m = SingleAreaLFC()
    _, f = m.simulate(loss_mw=0.0)
    assert np.allclose(f, m.f_nom)


def test_droop_offset_matches_formula():
    m = SingleAreaLFC()
    _, f = m.simulate(duration=90.0, loss_mw=1320.0)
    settled = f[-1]
    predicted = m.f_nom + steady_state_offset_hz(1320.0, m.s_base_mw, m.R, m.D, m.f_nom)
    assert abs(settled - predicted) < 1e-3


def test_generation_loss_pulls_frequency_below_nominal():
    m = SingleAreaLFC()
    _, f = m.simulate(loss_mw=1320.0)
    assert f[-1] < m.f_nom


def test_scaling_gives_realistic_offset_magnitude():
    m = SingleAreaLFC()
    _, f = m.simulate(loss_mw=1320.0)
    deviation_mhz = abs(f[-1] - m.f_nom) * 1000.0
    assert 30.0 < deviation_mhz < 300.0
