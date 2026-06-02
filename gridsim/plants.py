"""
Representative GB generation mix for the single-area LFC model.

Values represent a moderate-demand, high-wind GB dispatch snapshot (total online
generation about 30 GW). They are chosen to give realistic system inertia, primary
response stiffness, and rate of change of frequency, and are documented here so they
can be sourced and refined in the write-up. Inertia constants H are on each unit's
own MW base.

Modelling choices (stated plainly):
- Nuclear carries inertia but provides no primary droop response (runs baseload).
- Wind and interconnectors are inverter-based: no inherent inertia and, in this base
  snapshot, no primary response.
- Ramp rates are those used for sustained secondary (AGC) dispatch, in percent of own
  capacity per minute.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Generator:
    """A lumped generator of one fuel type."""

    name: str
    fuel: str
    capacity_mw: float
    H: float                    # inertia constant on own base [s]
    R: float                    # droop [pu freq / pu power]
    Tg: float                   # governor + turbine time constant [s]
    governs: bool = True        # provides primary (droop) response
    ramp_pct_per_min: float = 10.0  # secondary (AGC) ramp rate, % of own capacity / min


def gb_mix() -> list[Generator]:
    """A representative high-wind GB dispatch snapshot (about 30 GW online)."""
    return [
        Generator("Nuclear",         "nuclear", 5000.0, H=5.0, R=0.05, Tg=2.0, governs=False, ramp_pct_per_min=1.0),
        Generator("CCGT",            "gas",    12000.0, H=5.0, R=0.04, Tg=0.5, governs=True,  ramp_pct_per_min=20.0),
        Generator("OCGT",            "gas",     1500.0, H=3.0, R=0.04, Tg=0.3, governs=True,  ramp_pct_per_min=60.0),
        Generator("Coal/biomass",    "coal",    2000.0, H=4.0, R=0.05, Tg=1.0, governs=True,  ramp_pct_per_min=5.0),
        Generator("Hydro/pumped",    "hydro",   2000.0, H=3.0, R=0.04, Tg=0.3, governs=True,  ramp_pct_per_min=150.0),
        Generator("Wind",            "wind",    7000.0, H=0.0, R=0.04, Tg=0.5, governs=False, ramp_pct_per_min=100.0),
        Generator("Interconnectors", "hvdc",    2500.0, H=0.0, R=0.04, Tg=0.5, governs=False, ramp_pct_per_min=100.0),
    ]
