from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AGC:
    participation: dict        # generator name -> share of the AGC command (normalised to sum to 1)
    t_agc: float = 8.0         # target restoration time [s]; sets Ki = beta / t_agc
    kp_fraction: float = 0.10  # sets Kp = kp_fraction * beta
    t_actuator: float = 0.05   # actuator relaxation time [s]; small, so a_i is a clean rate limiter
    t_aw: float = 25.0         # anti-windup back-calculation time constant [s]

    def __post_init__(self):
        # Guard against a custom AGC that would over- or under-dispatch the secondary command.
        total = sum(self.participation.values())
        if total <= 0.0 or any(v < 0.0 for v in self.participation.values()):
            raise ValueError("AGC participation shares must be non-negative and sum to a positive value")
        self.participation = {k: v / total for k, v in self.participation.items()}   # normalise to 1

    def ki(self, beta: float) -> float:
        return beta / self.t_agc

    def kp(self, beta: float) -> float:
        return self.kp_fraction * beta

    def share(self, gen_name: str) -> float:
        return self.participation.get(gen_name, 0.0)


def flexible_fast_agc(t_agc: float = 8.0, kp_fraction: float = 0.10) -> AGC:
    return AGC(
        participation={
            "CCGT": 0.45,
            "Hydro/pumped": 0.30,
            "OCGT": 0.15,
            "Coal/biomass": 0.10,
        },
        t_agc=t_agc,
        kp_fraction=kp_fraction,
    )
