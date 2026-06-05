from gridsim.agc import flexible_fast_agc
from gridsim.fleet import FleetResponse
from gridsim.system import PowerSystem
from coupling import (ARBITRAGE, RECOVERY, RESERVE, RESPONSE, Supervisor, run_coupled)


def test_taper_endpoints_and_clamp():
    # Endpoints, midpoint, and clamps outside the recovery band
    s = Supervisor()
    assert abs(s.taper(49.80) - 1.0) < 1e-9      # full response at the trigger
    assert abs(s.taper(49.95) - 0.0) < 1e-9      # zero by the all-clear
    assert abs(s.taper(49.875) - 0.5) < 1e-9     # halfway
    assert s.taper(49.70) == 1.0                 # clamped below the trigger
    assert s.taper(50.00) == 0.0                 # clamped above the all-clear


def test_hysteresis_same_band_down_is_reserve_up_is_recovery():
    s = Supervisor()
    assert s.update(50.00) == ARBITRAGE
    assert s.update(49.85) == RESERVE            # drifting down, no event yet
    assert s.update(49.75) == RESPONSE           # event
    assert s.update(49.85) == RECOVERY           # same 49.85, now climbing back
    assert s.update(49.96) == ARBITRAGE          # all clear


def test_recovery_persists_until_all_clear():
    s = Supervisor()
    s.update(49.75)                              # RESPONSE
    assert s.update(49.82) == RECOVERY
    assert s.update(49.90) == RECOVERY           # still climbing, still recovery
    assert s.update(49.94) == RECOVERY
    assert s.update(49.95) == ARBITRAGE          # reaches the all-clear


def test_no_chatter_in_the_sticky_band():
    s = Supervisor()
    assert s.update(50.00) == ARBITRAGE
    for f in (49.94, 49.91, 49.93, 49.92, 49.94):   # all above the 49.90 reserve trigger
        assert s.update(f) == ARBITRAGE


def test_no_chatter_at_the_response_boundary():
    # dithering across 49.80 in recovery must not flip the label back to RESPONSE
    s = Supervisor()
    s.update(49.75)                                  # RESPONSE
    s.update(49.82)                                  # RECOVERY
    held = [s.update(f) for f in (49.81, 49.79, 49.81, 49.79, 49.81)]
    assert all(m == RECOVERY for m in held)          # the boundary now has hysteresis
    assert s.update(49.74) == RESPONSE               # a real re-dip past the re-arm gap still re-triggers


def test_coupled_run_exhibits_all_modes_without_chatter():
    system = PowerSystem(agc=flexible_fast_agc())
    sup = Supervisor()
    fleet = FleetResponse(p_fleet_mw=500.0, e_fleet_mwh=1000.0)
    _, f, modes, p, _ = run_coupled(system, sup, fleet, arb_setpoint_mw=-150.0,
                                    loss_mw=1800.0, trip_time=20.0, duration=80.0)
    assert {ARBITRAGE, RESERVE, RESPONSE, RECOVERY} <= set(modes)
    assert f.min() < 49.8                         # the event really crossed the trigger
    assert p.max() > 0.0                          # the battery discharged in response
    transitions = sum(1 for i in range(1, len(modes)) if modes[i] != modes[i - 1])
    assert transitions <= 8                       # no chatter
