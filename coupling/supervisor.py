from __future__ import annotations

from dataclasses import dataclass

ARBITRAGE = "ARBITRAGE"
RESERVE = "RESERVE"
RESPONSE = "RESPONSE"
RECOVERY = "RECOVERY"


@dataclass
class Supervisor:
    arb_hi_hz: float = 50.05       # top of the healthy band
    arb_clear_hz: float = 49.95    # all-clear on the way back up
    reserve_hz: float = 49.90      # caution threshold on the way down
    response_hz: float = 49.80     # event threshold on the way down
    resp_clear_gap_hz: float = 0.05  # re-arm RESPONSE only after a re-dip this far below response_hz
    mode: str = ARBITRAGE          # current state (the machine's memory)

    def update(self, f_hz: float) -> str:
        m = self.mode
        if m == ARBITRAGE:
            if f_hz < self.response_hz:
                m = RESPONSE
            elif f_hz < self.reserve_hz or f_hz > self.arb_hi_hz:
                m = RESERVE
        elif m == RESERVE:
            if f_hz < self.response_hz:
                m = RESPONSE
            elif self.arb_clear_hz <= f_hz <= self.arb_hi_hz:
                m = ARBITRAGE
        elif m == RESPONSE:
            if f_hz >= self.response_hz:
                m = RECOVERY
        elif m == RECOVERY:
            if f_hz < self.response_hz - self.resp_clear_gap_hz:   # genuine second dip, not a wiggle across 49.80
                m = RESPONSE
            elif f_hz >= self.arb_clear_hz:
                m = ARBITRAGE
        self.mode = m
        return m

    def taper(self, f_hz: float) -> float:
        frac = (self.arb_clear_hz - f_hz) / (self.arb_clear_hz - self.response_hz)
        return float(min(max(frac, 0.0), 1.0))
