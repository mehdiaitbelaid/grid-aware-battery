"""Tests for the multi-unit single-area model (PowerSystem)."""
import numpy as np

from gridsim.model import SingleAreaLFC
from gridsim.plants import Generator, gb_mix
from gridsim.system import PowerSystem


def test_system_inertia_is_capacity_weighted():
    """H_sys = sum(H_i * MW_i) / MW_base; only synchronous units contribute."""
    ps = PowerSystem()
    expected = sum(g.H * g.capacity_mw for g in gb_mix()) / ps.s_base_mw
    assert abs(ps.H_sys - expected) < 1e-9
    # wind and interconnectors (H=0) must not add inertia
    assert ps.H_sys < 4.0  # high-wind snapshot: noticeably below a 5 s machine


def test_offset_matches_effective_beta():
    """Settled frequency must match the analytic offset for this mix."""
    ps = PowerSystem()
    _, f = ps.simulate(duration=90.0, loss_mw=1320.0)
    predicted = ps.f_nom + ps.steady_state_offset_hz(1320.0)
    assert abs(f[-1] - predicted) < 1e-3


def test_nongoverning_units_provide_no_primary_response():
    """Nuclear, wind and interconnectors must contribute zero droop gain."""
    ps = PowerSystem()
    for g in ps.generators:
        if not g.governs:
            assert ps.droop_gain(g) == 0.0


def test_reduces_to_single_machine():
    """One aggregate governing unit must reproduce SingleAreaLFC exactly."""
    agg = Generator("agg", "agg", 30000.0, H=5.0, R=0.05, Tg=0.3, governs=True)
    ps = PowerSystem(generators=[agg], D=1.0, s_base_mw=30000.0)
    single = SingleAreaLFC(H=5.0, D=1.0, R=0.05, Tg=0.3, s_base_mw=30000.0)

    assert abs(ps.H_sys - single.H) < 1e-9
    assert abs(ps.beta - (1.0 / single.R + single.D)) < 1e-9

    _, f_ps = ps.simulate(duration=90.0, loss_mw=1320.0)
    _, f_single = single.simulate(duration=90.0, loss_mw=1320.0)
    assert abs(f_ps[-1] - f_single[-1]) < 1e-3
