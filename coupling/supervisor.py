"""
Supervisor state machine (Tier 3 Stage 3).

Decides, from the live grid frequency, which job the battery is doing:
  ARBITRAGE  frequency healthy                       -> follow the market dispatch
  RESERVE    frequency drifting low, not an event    -> stop charging, hold ready
  RESPONSE   frequency below 49.8 Hz (an event)      -> full frequency response
  RECOVERY   climbing back from an event             -> taper the response back out

Every boundary has hysteresis: the threshold to enter a more alert state (going down) sits
below the threshold to clear back to a calmer one (coming up). Written as a per-state
machine, so each mode has its own exit tests and nothing can chatter around a single line:

  enter RESERVE  below 49.90,  clear to ARBITRAGE at/above 49.95   (a 50 mHz sticky band)
  enter RESPONSE below 49.80,  leave to RECOVERY  at/above 49.80
  RECOVERY clears to ARBITRAGE at/above 49.95, and re-enters RESPONSE if it dips again

RECOVERY also tapers the response to zero by the 49.95 all-clear, so the AGC finishes the
restoration cleanly (the cure for the Stage 2 settle-drag). Frequencies are in Hz.
"""
from __future__ import annotations

from dataclasses import dataclass

ARBITRAGE = "ARBITRAGE"
RESERVE = "RESERVE"
RESPONSE = "RESPONSE"
RECOVERY = "RECOVERY"


@dataclass
class Supervisor:
    """Four-mode state machine that switches the battery between arbitrage and response."""

    arb_hi_hz: float = 50.05       # top of the healthy band
    arb_clear_hz: float = 49.95    # all-clear: return to ARBITRAGE coming back up
    reserve_hz: float = 49.90      # caution: enter RESERVE going down
    response_hz: float = 49.80     # event: enter RESPONSE going down
    mode: str = ARBITRAGE          # current state (the machine's memory)

    def update(self, f_hz: float) -> str:
        """Advance the state machine one step from the current frequency, return the mode."""
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
            if f_hz < self.response_hz:
                m = RESPONSE
            elif f_hz >= self.arb_clear_hz:
                m = ARBITRAGE
        self.mode = m
        return m

    def taper(self, f_hz: float) -> float:
        """Recovery taper: 1.0 at the response trigger, 0.0 at the all-clear, clamped to [0, 1]."""
        frac = (self.arb_clear_hz - f_hz) / (self.arb_clear_hz - self.response_hz)
        return float(min(max(frac, 0.0), 1.0))
