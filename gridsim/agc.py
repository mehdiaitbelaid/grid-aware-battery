"""
Automatic Generation Control (AGC): the secondary frequency controller.

The AGC applies a PI correction to the area control error (here the frequency
error), splits the resulting secondary power command across units by participation
factor, and lets each unit move toward its share at its own ramp limit.
Back-calculation anti-windup stops the integral running away while slow units are
still ramping.

Gain policy (justified, not hand-tuned): the integral gain is derived from a target
restoration time, Ki = beta / t_agc, where beta is the system frequency response
characteristic. The proportional gain is a conservative fraction of beta, so it has
the same physical scale as the system stiffness instead of being an arbitrary MW/Hz
number. t_agc, kp_fraction, and the participation split are the engineering choices.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AGC:
    """Secondary control configuration."""

    participation: dict        # generator name -> share of the AGC command (sums to 1)
    t_agc: float = 8.0         # target restoration time [s]; sets Ki = beta / t_agc
    kp_fraction: float = 0.10  # sets Kp = kp_fraction * beta
    t_actuator: float = 0.05   # actuator relaxation time [s]; small, so a_i is a clean rate limiter
    t_aw: float = 25.0         # anti-windup back-calculation time constant [s]

    def ki(self, beta: float) -> float:
        """Integral gain derived from the target restoration time and system beta."""
        return beta / self.t_agc

    def kp(self, beta: float) -> float:
        """Proportional gain on frequency error, scaled to the system stiffness."""
        return self.kp_fraction * beta

    def share(self, gen_name: str) -> float:
        """Participation share for a named generator (0 if it does not respond)."""
        return self.participation.get(gen_name, 0.0)


def flexible_fast_agc(t_agc: float = 8.0, kp_fraction: float = 0.10) -> AGC:
    """The flexible-fast participation split: gas and hydro lead, nuclear/wind at zero."""
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
