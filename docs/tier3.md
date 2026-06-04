# Tier 3: market reserve (Stage 1) and physical response (Stage 2)

## Purpose
Tier 3 asks the battery to connect market behaviour to grid frequency. This first stage
implements the market-side part: the arbitrage optimiser can reserve upward discharge
capacity for frequency response, then quantify how much arbitrage profit is sacrificed.

This is not yet the full mode-switching supervisor. It is the availability frontier that
the supervisor would trade against.

## Method
The battery LP now accepts two optional reserve constraints:

- `reserve_power_kw`: keep this much upward discharge headroom every hour.
- `reserve_energy_kwh`: keep enough stored energy to sustain the reserve for a chosen
  duration.

For the current experiment, the sustain duration is 30 minutes:

```text
reserve_energy_kwh = reserve_power_kw * 0.5 h / eta_dis
```

The sweep uses perfect foresight prices deliberately. That isolates the price of the
reserve constraint from Tier 2 forecast error.

## Result

| reserve | power | energy floor | profit | profit kept |
|---:|---:|---:|---:|---:|
| 0% | 0 kW | 0.0 kWh | GBP 16,176 | 100.0% |
| 20% | 200 kW | 106.6 kWh | GBP 14,184 | 87.7% |
| 50% | 500 kW | 266.5 kWh | GBP 10,807 | 66.8% |
| 80% | 800 kW | 426.4 kWh | GBP 6,986 | 43.2% |
| 100% | 1000 kW | 533.0 kWh | GBP 0 | 0.0% |

The curve is convex: low reserve levels are relatively cheap, while the final slices of
reserve remove the power needed for the most valuable arbitrage trades.

## Interpretation
Reserving 200 kW for frequency response costs about GBP 1,992 over 60 days, or 12.3% of
the perfect foresight arbitrage value. Reserving 500 kW keeps about two thirds of the
arbitrage profit while guaranteeing half the battery rating as upward response for
30 minutes.

## Forecast sensitivity: who actually pays for the reserve
The Pareto above uses perfect foresight, so it is the theoretical cost of the reserve. To
see what a real operator would pay, the same sweep was run with the realistic same-hour
average forecast driving the rolling MPC (`make_tier3_sensitivity.py`,
`results/tier3_pareto_sensitivity.csv`).

| reserve | perfect foresight | realistic forecast |
|---:|---:|---:|
| 0% | GBP 16,176 (100%) | GBP 3,927 (100%) |
| 20% | GBP 14,184 (87.7%) | GBP 3,901 (99.3%) |
| 40% | GBP 11,950 (73.9%) | GBP 3,979 (101.3%) |
| 60% | GBP 9,620 (59.5%) | GBP 4,134 (105.3%) |
| 80% | GBP 6,986 (43.2%) | GBP 4,131 (105.2%) |
| 100% | GBP 0 | GBP -24 |

The two curves differ in shape, not just level. Under perfect foresight the reserve is
expensive and convex. Under the realistic forecast it is almost free: profit stays roughly
flat up to 80% reserve and only collapses at 100%.

The reason is that the realistic MPC already captures only about a quarter of the
achievable arbitrage, and the value it does capture comes from the large, reliable daily
price swing, which rarely needs full battery power. The aggressive trades a reserve would
block are the marginal, uncertain ones the weak forecast cannot act on with confidence
anyway, so the reserved capacity was mostly idle. The small rise in the middle is the
reserve acting as a guardrail: limiting trade size curbs the overconfident bets the noisy
forecast makes, so realised profit edges up slightly. That increase is small and within
forecast noise, so it should not be read as the reserve being profitable.

Takeaway: the cost of frequency response reserve depends on forecast quality. The perfect
foresight frontier is an upper bound on that cost. For a real operator with an imperfect
forecast, reserving capacity is close to free up to a large fraction of rated power,
because the arbitrage it displaces is value the forecast could not have captured. See
`plots/tier3_pareto_sensitivity.png`.

## Stage 1 limitations
- This is an availability constraint, not yet a live low-frequency dispatch controller.
- The sweep uses perfect foresight to isolate the reserve cost; realistic forecast-based
  operation would sit lower in absolute profit.
- The battery is the original 1 MW / 2 MWh asset. A visible system-frequency impact would
  require scaling to an aggregated fleet or explicitly reporting per-MW impact.

## Stage 2: what the reserve buys physically
Stage 1 sized the reserve in the market. Stage 2 puts that reserved power to work inside the
Tier 1 frequency model and measures what it buys. The battery is scaled to an aggregated
fleet, because a single 1 MW unit is invisible on a 30 GW system; the economics stay per MW,
only the physics is scaled.

The fleet responds two ways (`gridsim/fleet.py`), both entering the swing equation directly
(`gridsim/system.py`):
- synthetic droop: inject power proportional to the frequency drop, reaching the full
  reserved power by 0.5 Hz of deviation, capped at the reserve. It enters as an extra power
  injection and lifts the nadir.
- synthetic inertia: emulate 6 s of inertia on the fleet rating. It enters as a larger
  effective system inertia and lowers the initial RoCoF.

### Fleet-size sweep (1320 MW trip)
| fleet | nadir | RoCoF | recovery |
|---:|---:|---:|---:|
| 0 | 49.808 Hz | -0.318 Hz/s | 21.8 s |
| 500 MW | 49.828 Hz | -0.309 Hz/s | 24.3 s |
| 1000 MW | 49.844 Hz | -0.301 Hz/s | 26.2 s |
| 2000 MW | 49.868 Hz | -0.285 Hz/s | 29.1 s |

Nadir rises strongly with fleet size, about +30 mHz per GW. RoCoF improves only weakly, about
10% even at 2 GW, because synthetic inertia from even a large fleet adds little stored energy
to a 30 GW system. A battery is a strong lever on the dip and a weak one on the slope.

### Severe 1800 MW trip
The 1800 MW trip is the case Tier 1 held above the floor but missed the 30 s target on.
| fleet | nadir | recovery | meets 30 s |
|---:|---:|---:|:--:|
| 0 | 49.740 Hz | 34.0 s | no |
| 500 MW | 49.768 Hz | 22.9 s | yes |
| 1000 MW | 49.791 Hz | 27.1 s | yes |
| 2000 MW | 49.824 Hz | 32.9 s | no |

A 500 MW fleet rescues the case: recovery drops from 34 s to 22.9 s, inside the target,
because the lifted nadir leaves less for the AGC to claw back. But a 2000 MW fleet, despite
the best nadir, misses the target again at 32.9 s: too much fast response makes the system
heavy and the undamped droop overshoots the restoration, so the settle drags. There is a
sweet spot. This tension motivates the Stage 3 supervisor, which would take the dip benefit
and then taper the response as frequency normalises.

### Stage 2 scope
- The fleet provides only upward (discharge) response to low-frequency events.
- Synthetic inertia is modelled as an addition to the system inertia, the exact resolution of
  a df/dt response; a real implementation must filter the noisy df/dt measurement.
- The fleet size and droop envelope are representative; the sweeps show the sensitivity.

## Stage 3: the supervisor
Stages 1 and 2 left two halves: the market reserve and the physical response. Stage 3 is the
controller that runs them together, deciding moment to moment, from the live frequency, which
job the battery does. It is a four-mode state machine (`coupling/supervisor.py`):

- ARBITRAGE (healthy frequency): follow the market dispatch.
- RESERVE (drifting low): stop charging, hold ready.
- RESPONSE (below 49.8 Hz): drop arbitrage, inject the reserved power.
- RECOVERY (climbing back): taper the response to zero by the all-clear, then resume arbitrage.

Every boundary has hysteresis: the threshold to enter a more alert state going down sits below
the threshold to clear back coming up, so the battery cannot chatter around a line. The
RECOVERY taper hands the last of the restoration back to the AGC, the fix for the Stage 2
settle-drag.

### The event timeline
One severe 1800 MW trip while the battery is charging at 150 MW for arbitrage
(`make_tier3_stage3.py`, `plots/tier3_stage3_timeline.png`):

| time since trip | mode | what the battery does |
|---|---|---|
| +0.00 s | ARBITRAGE | charging 150 MW |
| +0.24 s | RESERVE | cancels charging, holds ready |
| +0.61 s | RESPONSE | discharges up to 206 MW to support the grid |
| +1.46 s | RECOVERY | tapers the response as frequency climbs |
| +14.71 s | ARBITRAGE | resumes charging |

The supervised battery lifts the nadir to 49.779 Hz, against 49.740 Hz with no battery, and
hands control back cleanly. A first version chattered because one boundary lacked hysteresis;
the per-state machine fixes it and a test guards against regression.

### Stage 3 scope
- One under-frequency event is shown; the same logic is symmetric for over-frequency.
- The response deployed is the Stage 2 droop; synthetic inertia is characterised in Stage 2.
- The supervisor is event-gated, responding below 49.8 Hz rather than to every wiggle, which
  is why frequency response sits so lightly on arbitrage: the Stage 1 sensitivity made physical.
