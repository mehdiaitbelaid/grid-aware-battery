from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Generator:
    name: str
    fuel: str
    capacity_mw: float
    H: float                    # inertia constant on own base [s]
    R: float                    # droop [pu freq / pu power]
    Tg: float                   # governor + turbine time constant [s]
    governs: bool = True        # provides primary (droop) response
    ramp_pct_per_min: float = 10.0  # secondary (AGC) ramp rate, % of own capacity / min


def gb_mix() -> list[Generator]:
    return [
        Generator("Nuclear",         "nuclear", 5000.0, H=5.0, R=0.05, Tg=2.0, governs=False, ramp_pct_per_min=1.0),
        Generator("CCGT",            "gas",    12000.0, H=5.0, R=0.04, Tg=0.5, governs=True,  ramp_pct_per_min=20.0),
        Generator("OCGT",            "gas",     1500.0, H=3.0, R=0.04, Tg=0.3, governs=True,  ramp_pct_per_min=60.0),
        Generator("Coal/biomass",    "coal",    2000.0, H=4.0, R=0.05, Tg=1.0, governs=True,  ramp_pct_per_min=5.0),
        Generator("Hydro/pumped",    "hydro",   2000.0, H=3.0, R=0.04, Tg=0.3, governs=True,  ramp_pct_per_min=150.0),
        Generator("Wind",            "wind",    7000.0, H=0.0, R=0.04, Tg=0.5, governs=False, ramp_pct_per_min=100.0),
        Generator("Interconnectors", "hvdc",    2500.0, H=0.0, R=0.04, Tg=0.5, governs=False, ramp_pct_per_min=100.0),
    ]
