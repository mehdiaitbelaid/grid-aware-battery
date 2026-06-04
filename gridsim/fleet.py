from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FleetResponse:
    p_fleet_mw: float = 500.0       # fleet rated power [MW]
    e_fleet_mwh: float = 1000.0     # fleet energy [MWh] (sets duration; unused by the swing model)
    reserve_mw: float | None = None # upward power held available for response [MW] (None = full fleet)
    droop_full_hz: float = 0.5      # frequency drop at which droop delivers the full reserve [Hz]
    h_batt_s: float = 6.0           # emulated synthetic inertia constant on the fleet rating [s]
    deadband_hz: float = 0.015      # respond only once frequency leaves this band [Hz]

    @property
    def reserve(self) -> float:
        return self.p_fleet_mw if self.reserve_mw is None else self.reserve_mw

    def added_H_s(self, s_base_mw: float) -> float:
        return self.h_batt_s * self.p_fleet_mw / s_base_mw

    def injection_pu(self, f_hz: float, f_nom: float, s_base_mw: float) -> float:
        dev = f_nom - f_hz                       # Hz below nominal (positive = under-frequency)
        if dev <= self.deadband_hz:
            return 0.0
        gain_mw_per_hz = self.reserve / self.droop_full_hz
        p_mw = min(self.reserve, gain_mw_per_hz * (dev - self.deadband_hz))
        return p_mw / s_base_mw
