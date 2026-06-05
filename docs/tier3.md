# Tier 3: market reserve (Stage 1) and physical response (Stage 2)

## Purpose
Tier 3 asks the battery to connect market behaviour to grid frequency. In this first stage
I implement the market-side part: the arbitrage optimiser can reserve upward discharge
capacity for frequency response, and I then quantify how much arbitrage profit that sacrifices.

Stage 1 (this section) builds the availability frontier in the market. Stages 2 and 3 below
add the physical fleet response and the supervisor that trades against it.

## Method
The battery LP now accepts two optional reserve constraints:

- `reserve_power_kw`: keep this much upward discharge headroom every hour.
- `reserve_energy_kwh`: keep enough stored energy to sustain the reserve for a chosen
  duration.

For the current experiment, the sustain duration is 30 minutes:

```text
reserve_energy_kwh = reserve_power_kw * 0.5 h / eta_dis
```

I use perfect foresight prices in the sweep deliberately. That isolates the price of the
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
arbitrage profit while holding half the battery rating as upward response for
30 minutes.

## Forecast sensitivity: who actually pays for the reserve
The Pareto above uses perfect foresight, so it is the theoretical cost of the reserve. To
see what a real operator would pay, I ran the same sweep with the realistic same-hour
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
expensive and convex. Under the realistic forecast it costs little in this run: profit stays roughly
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
forecast, reserving capacity can cost little up to a large fraction of rated power,
because the arbitrage it displaces is value the forecast could not have captured. See
`plots/tier3_pareto_sensitivity.png`.

## Stage 1 limitations
- This is an availability constraint, not yet a live low-frequency dispatch controller.
- The sweep uses perfect foresight to isolate the reserve cost. Realistic forecast-based
  operation would sit lower in absolute profit.
- The battery is the original 1 MW / 2 MWh asset. A visible system-frequency impact would
  require scaling to an aggregated fleet or explicitly reporting per-MW impact.

## Stage 2: what the reserve buys physically
In Stage 1 I sized the reserve in the market. In Stage 2 I put that reserved power to work inside the
Tier 1 frequency model and measured what it buys. I scale the battery to an aggregated
fleet, because a single 1 MW unit is invisible on a 30 GW system. The economics stay per MW,
only the physics is scaled.

The fleet responds two ways (`gridsim/fleet.py`), both entering the swing equation directly
(`gridsim/system.py`):
- synthetic droop: inject power proportional to the frequency drop, reaching the full
  reserved power by 0.5 Hz of deviation, capped at the reserve. It enters as an extra power
  injection and lifts the nadir.
- synthetic inertia: emulate 6 s of inertia on the fleet rating, an effective inertia
  approximation that enters as a larger effective system inertia and lowers the initial
  RoCoF. A real inverter would filter a df/dt measurement; the constant added inertia used
  here is a first-order approximation, not an inverter-control model.

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
This is the case Tier 1 held above the floor but missed the 30 s target on.
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
middle case. This tension is what motivated the Stage 3 supervisor, which takes the dip benefit
and then tapers the response as frequency normalises.

### Stage 2 scope
- The fleet droop is symmetric: it discharges to support low frequency and absorbs (charges)
  to contain over-frequency, shown in the over-frequency run below.
- Synthetic inertia is modelled as an addition to the system inertia, the exact resolution of
  a df/dt response. A real implementation must filter the noisy df/dt measurement.
- The fleet size and droop envelope are representative. The sweeps show the sensitivity.

### Over-frequency, response speed, and the full surface
The fleet droop is symmetric, so an over-frequency event is contained the same way: a 1320 MW
generation surplus pushes frequency to a 50.19 Hz zenith, the mirror of the 49.81 nadir, and
the fleet absorbs by charging to pull it back to 50.17 (`make_tier3_overfreq.py`). Response
speed is a second axis beyond reserved power: at a fixed 500 MW reserve, a fast ramp gives
the full nadir lift while a 50 MW/s ramp arrives too late to help (`make_tier3_speed.py`).
Sweeping reserve and ramp rate together (`make_tier3_surface.py`,
`plots/tier3_surface.png`) shows the two interact: at 50 MW/s the nadir is 49.745 Hz whatever
the reserve, because the response arrives after the dip, while at 1000 MW/s it climbs from
49.754 Hz at 250 MW reserve to 49.815 Hz at 2 GW. A large reserve is wasted without speed,
and speed has little to give without reserve. Each reserve level also has an arbitrage cost
from the Stage 1 frontier (a separate result; this surface holds only the nadir), so the two
together describe the three-way trade-off a flexibility provider faces: arbitrage profit
against response availability against response speed. The droop envelope, full response by
0.5 Hz of deviation, is shaped like NESO's Dynamic Containment; NESO also runs Dynamic
Moderation and Dynamic Regulation, each with published deadband and speed requirements a
production version would match.

## Stage 3: the supervisor
Stages 1 and 2 left two halves: the market reserve and the physical response. In Stage 3 I built the
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
| +0.25 s | RESERVE | cancels charging, holds ready |
| +0.62 s | RESPONSE | discharges up to 207 MW to support the grid |
| +1.47 s | RECOVERY | tapers the response as frequency climbs |
| +14.77 s | ARBITRAGE | resumes charging |

The supervised battery lifts the nadir to 49.778 Hz, against 49.740 Hz with no battery, and
hands control back without chatter. My first version chattered because one boundary lacked hysteresis.
The per-state machine fixes it and a test guards against regression.

### Stage 3 scope
- I show a single under-frequency event through the supervisor. The over-frequency case is
  shown in the fleet model above (symmetric droop); the supervisor's mode logic here is the
  low-frequency side, and a mirror high-frequency mode would complete it.
- I treat the arbitrage setpoint as scheduled demand, so only the battery's deviation from
  it moves frequency, and the scheduled charging does not disturb frequency before the trip.
- The response deployed is the Stage 2 droop. I characterise synthetic inertia in Stage 2.
- The supervisor is event-gated, responding below 49.8 Hz rather than to every wiggle, which
  is why frequency response sits so lightly on arbitrage: the Stage 1 sensitivity made physical.

## Is it worth it? Net value
Stage 1 priced the cost of being available; this prices the revenue. Reserving 500 kW costs
GBP 5,369 of perfect-foresight arbitrage over the 60 days, while that same 500 kW held in
NESO's Dynamic Containment earns the DC availability price times the 1440 hours, so the
break-even DC price is about GBP 7.5/MW/h (`make_tier3_value.py`, `plots/tier3_value.png`). DC
has cleared roughly GBP 5 to GBP 15/MW/h in its busy years and lower since the market
saturated, so against perfect foresight this is a price-dependent call. The sensitivity result
sharpens it: under a realistic forecast the reserve is nearly free (about -GBP 130 here), so
the DC revenue is almost pure profit and providing response is worth it across essentially the
whole historical range. Caveat: this assumes the capacity wins DC availability for the whole
period; DC is auction cleared in 4-hour EFA blocks, so the figure is an illustrative upper
bound, not guaranteed income.
