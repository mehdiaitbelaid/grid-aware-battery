"""
Aggregated battery fleet that provides fast frequency response to the grid model.

Tier 3 Stage 2: the reserved battery power from Stage 1 is put to work inside the Tier 1
frequency model. The fleet responds two ways once frequency leaves a small deadband:

  - synthetic droop: inject power in proportion to how far frequency is below nominal,
    reaching the full reserved power at `droop_full_hz` of deviation, capped at the reserve.
    Same law as a governor's droop, run by inverter electronics, and it lifts the nadir
    (the depth of the dip).
  - synthetic inertia: emulate `h_batt_s` seconds of inertia on the fleet rating. In the
    swing equation this simply adds to the system inertia, which lowers the initial RoCoF
    (the steepness of the fall).

A single 1 MW battery is invisible on a 30 GW system, so the fleet is an aggregation of
many batteries. The Stage 1 economics are reported per MW; only this physical model is
scaled up. Only the low-frequency (discharge) response is modelled here.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FleetResponse:
    """Parameters of the aggregated battery fleet's fast frequency response."""

    p_fleet_mw: float = 500.0       # fleet rated power [MW]
    e_fleet_mwh: float = 1000.0     # fleet energy [MWh] (sets duration; unused by the swing model)
    reserve_mw: float | None = None # upward power held available for response [MW] (None = full fleet)
    droop_full_hz: float = 0.5      # frequency drop at which droop delivers the full reserve [Hz]
    h_batt_s: float = 6.0           # emulated synthetic inertia constant on the fleet rating [s]
    deadband_hz: float = 0.015      # respond only once frequency leaves this band [Hz]

    @property
    def reserve(self) -> float:
        """Upward power available for response [MW]."""
        return self.p_fleet_mw if self.reserve_mw is None else self.reserve_mw

    def added_H_s(self, s_base_mw: float) -> float:
        """Synthetic inertia expressed as an addition to the system inertia constant [s]."""
        return self.h_batt_s * self.p_fleet_mw / s_base_mw

    def injection_pu(self, f_hz: float, f_nom: float, s_base_mw: float) -> float:
        """Synthetic droop injection, per-unit on the system base, under-frequency only.

        Power rises linearly with the frequency drop beyond the deadband and saturates at
        the reserved power. Returns 0 at or above nominal: this model provides only upward
        (discharge) response to low-frequency events.
        """
        dev = f_nom - f_hz                       # Hz below nominal (positive = under-frequency)
        if dev <= self.deadband_hz:
            return 0.0
        gain_mw_per_hz = self.reserve / self.droop_full_hz
        p_mw = min(self.reserve, gain_mw_per_hz * (dev - self.deadband_hz))
        return p_mw / s_base_mw
