import numpy as np

from gridsim.model import SingleAreaLFC
from gridsim.plants import Generator, gb_mix
from gridsim.system import PowerSystem


def test_system_inertia_is_capacity_weighted():
    ps = PowerSystem()
    expected = sum(g.H * g.capacity_mw for g in gb_mix()) / ps.s_base_mw
    assert abs(ps.H_sys - expected) < 1e-9
    # Wind and interconnectors have H=0 in this snapshot
    assert ps.H_sys < 4.0  # high-wind snapshot, so noticeably below a 5 s machine


def test_offset_matches_effective_beta():
    ps = PowerSystem(deadband_hz=0.0)
    _, f = ps.simulate(duration=90.0, loss_mw=1320.0)
    predicted = ps.f_nom + ps.steady_state_offset_hz(1320.0)
    assert abs(f[-1] - predicted) < 1e-3


def test_nongoverning_units_provide_no_primary_response():
    ps = PowerSystem()
    for g in ps.generators:
        if not g.governs:
            assert ps.droop_gain(g) == 0.0


def test_deadband_deepens_the_offset():
    loss = 1320.0
    no_db = PowerSystem(deadband_hz=0.0).simulate(duration=90.0, loss_mw=loss)[1][-1]
    with_db = PowerSystem(deadband_hz=0.015).simulate(duration=90.0, loss_mw=loss)[1][-1]
    assert with_db < no_db
    assert (no_db - with_db) < 0.05


def test_reduces_to_single_machine():
    agg = Generator("agg", "agg", 30000.0, H=5.0, R=0.05, Tg=0.3, governs=True)
    ps = PowerSystem(generators=[agg], D=1.0, s_base_mw=30000.0, deadband_hz=0.0)
    single = SingleAreaLFC(H=5.0, D=1.0, R=0.05, Tg=0.3, s_base_mw=30000.0)

    assert abs(ps.H_sys - single.H) < 1e-9
    assert abs(ps.beta - (1.0 / single.R + single.D)) < 1e-9

    _, f_ps = ps.simulate(duration=90.0, loss_mw=1320.0)
    _, f_single = single.simulate(duration=90.0, loss_mw=1320.0)
    assert abs(f_ps[-1] - f_single[-1]) < 1e-3
