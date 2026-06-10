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
| fleet | nadir | RoCoF 500 ms avg | RoCoF peak | recovery |
|---:|---:|---:|---:|---:|
| 0 | 49.808 Hz | -0.271 Hz/s | -0.318 Hz/s | 21.8 s |
| 500 MW | 49.828 Hz | -0.253 Hz/s | -0.309 Hz/s | 24.3 s |
| 1000 MW | 49.844 Hz | -0.236 Hz/s | -0.301 Hz/s | 26.2 s |
| 2000 MW | 49.868 Hz | -0.209 Hz/s | -0.285 Hz/s | 29.1 s |

Nadir rises strongly with fleet size, about +30 mHz per GW. RoCoF improves more modestly: the
peak slope eases about 10% and the 500 ms average about 23% at 2 GW, because synthetic inertia
from even a large fleet adds little stored energy to a 30 GW system. A battery is a strong lever
on the dip and a weaker one on the slope.

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

Every boundary that could chatter has hysteresis: the threshold to enter a more alert state going
down sits below the threshold to clear back coming up. The RESPONSE to RECOVERY hand-off is
single-sided at 49.80, but it does not chatter because the taper is 1.0 there, so the response power
is continuous across it, and the re-arm from RECOVERY back to RESPONSE has a 50 mHz gap. The
RECOVERY taper hands the last of the restoration back to the AGC, the fix for the Stage 2
settle-drag. These bands are sized for clean frequency: fed a raw sensor signal with tens of mHz of
noise the modes chatter, so a production version would low-pass the measurement first.

### The event timeline
One severe 1800 MW trip while the battery is charging at 150 MW for arbitrage
(`make_tier3_stage3.py`, `plots/tier3_stage3_timeline.png`):

| time since trip | mode | what the battery does |
|---|---|---|
| +0.00 s | ARBITRAGE | charging 150 MW |
| +0.25 s | RESERVE | cancels charging, holds ready |
| +0.64 s | RESPONSE | discharges up to 205 MW to support the grid |
| +1.48 s | RECOVERY | tapers the response as frequency climbs |
| +14.78 s | ARBITRAGE | resumes charging |

The supervised battery lifts the nadir to 49.780 Hz, against 49.740 Hz with no battery, and
hands control back without chatter. My first version chattered because one boundary lacked hysteresis.
The per-state machine fixes it and a test guards against regression.

The coupled run is state-coupled both ways. It carries the Stage 2 synthetic inertia (attached as a
passive inertia-only fleet so the supervisor still owns the droop, with no double counting) and it
tracks the fleet state of charge, debiting the energy the response delivers and holding it above a
reserve floor sized to sustain the reserve for 30 minutes. The floor is a hard state-of-charge guard,
not a sustained-rate throttle. On this event the response delivers about 0.2 MWh, well under 0.1% of
the floor, so deliverability is never at risk: the state-of-charge panel in
`plots/tier3_stage3_timeline.png` sits flat above the floor. (The physics sizes the floor as power
times duration; the Stage 1 LP divides by discharge efficiency, a few percent more. The difference
never binds, since the operating SoC sits far above either.) The inertia is a small lever here, worth
about 2 mHz of nadir and modelled as always available, consistent with the Stage 2 finding that a
battery helps the dip far more than the slope.

### Stage 3 scope
- I show a single under-frequency event through the supervisor. On an over-frequency surplus the
  RESERVE state holds the battery's absorbing charge rather than cancelling it, so the supervisor
  never makes a surplus worse, though it does not yet charge harder to actively contain it; an
  active mirrored high-frequency mode (the symmetric droop charging into the surplus) would complete
  that. The over-frequency containment shown in the fleet model above assumes no charge-headroom
  limit, so its symmetry with the nadir is exact by construction rather than demonstrated under
  storage limits.
- I treat the arbitrage setpoint as scheduled demand, so only the battery's deviation from
  it moves frequency, and the scheduled charging does not disturb frequency before the trip.
- The coupled run deploys the supervised droop and the Stage 2 synthetic inertia together, and
  tracks the fleet energy against a reserve floor (see above). The arbitrage setpoint is still a
  constant stand-in for the hourly MPC dispatch, so wiring the live MPC schedule into the coupled
  loop is the remaining step toward a full hybrid simulation.
- Sweeping the supervisor's own response threshold (`make_tier3_supervisor_sweep.py`,
  `plots/tier3_supervisor_sweep.png`) is a second design axis beyond reserve size: a threshold
  below the natural dip never deploys the reserve, while above it a higher threshold deploys
  sooner for a slightly better nadir, and no setting chatters (at most 4 transitions).
- The supervisor is event-gated, responding below 49.8 Hz rather than to every wiggle, which
  is why frequency response sits so lightly on arbitrage: the Stage 1 sensitivity made physical.

## Is it worth it? Net value
Stage 1 priced the cost of being available; this prices the revenue, using the DC availability
price that ships in the dataset (`ancillary_availability_gbp_per_mw_per_h`) instead of a hand
cited number. The availability price averages GBP 8.06/MW/h (range 1.00 to 16.17), above the GBP
7.46/MW/h break-even, so the 500 kW earns GBP 5,800 over the 60 days. Against the perfect-foresight
cost of reserving (GBP 5,369, the upper bound on the arbitrage given up), that nets GBP +431. I
lead with this number because it holds even against the most arbitrage you could ever lose to
reserving, on a single basis. Under a realistic forecast the reserve costs about nothing: the raw
sensitivity value is GBP -130, which the Stage 1 sensitivity flags as within forecast noise, so I
floor it at zero rather than bank it as a gain. On that basis the GBP 5,800 is essentially all net.
Either way it pays (`make_tier3_value.py`, `plots/tier3_value.png`, `results/tier3_value.csv`).
Caveats: 500 kW is below the 1 MW minimum DC offer, so read it as a share of an aggregated fleet,
not a standalone bid; DC is auction cleared in 4-hour EFA blocks with eligibility, bidding,
clearing, metering, state-of-charge, and performance rules, so this is an upper bound, not
realisable income; the revenue assumes the reserve clears at the availability price every hour; and
the perfect-foresight cost and the realistic cost sit on different arbitrage baselines, which is why
I headline the single-basis +431. The dataset also carries an `imbalance_price_gbp_per_mwh` series,
which a fuller model would use to value the energy deviation during an event; I price it as a
ceiling in the extensions below.

## Degradation sensitivity
The net value above ignores battery wear. Cycling a battery consumes cycle life, so a real
operator pays a throughput cost per MWh discharged, a standard cycle proxy that folds in
charge-side wear. I add this as an optional term in the
arbitrage objective (`solve_arbitrage(..., degradation_cost_per_mwh=...)`, default 0 so the
baseline is unchanged) and sweep it, because the cost is uncertain. A defensible basis is the
cell capex divided by the cycle life: at about GBP 100 to 150 per kWh and 5,000 to 10,000 full
cycles, that is roughly GBP 10 to 20 per MWh discharged (`make_tier3_degradation.py`,
`results/tier3_degradation.csv`, `plots/tier3_degradation.png`).

| degradation cost | arbitrage (perfect foresight) | cycling | break-even DC price |
|---:|---:|---:|---:|
| GBP 0/MWh | GBP 16,176 | 293 MWh | GBP 7.46/MW/h |
| GBP 5/MWh | GBP 14,937 | 208 MWh | GBP 6.97/MW/h |
| GBP 10/MWh | GBP 14,011 | 168 MWh | GBP 6.65/MW/h |
| GBP 20/MWh | GBP 12,482 | 142 MWh | GBP 6.18/MW/h |
| GBP 25/MWh | GBP 11,791 | 135 MWh | GBP 5.98/MW/h |

Two things stand out. At a central GBP 10 per MWh, cycling falls 43% but profit only 13%,
because the trades degradation removes are the marginal, low-spread ones, not the large daily
swing. And the reserve break-even DC price falls with it, from GBP 7.46 to GBP 6.65/MW/h. The
reason is structural: arbitrage cycles hard every day while a frequency reserve sits idle until
a rare event, so pricing wear hits arbitrage harder than it hits the reserve. Accounting for
degradation therefore strengthens the frequency-response case rather than weakening it. The
convention is cost per MWh discharged, and like the Stage 1 frontier this uses perfect
foresight, so it is the theoretical bound, not a realised operating cost.

## Co-optimizing the reserve
The net value above fixes the reserve at 500 kW and then prices it. That level is itself a choice,
and the frontier I swept is one frozen setting of it. If instead the reserve `r` is a decision
variable, one value per 4-hour EFA block, co-optimized with the arbitrage in the same LP (`avail[t]*r[t]`
added to the objective, `pdis[t]-pch[t] <= p_max - r[t]` and `e[t] >= r[t]*0.5/eta` as constraints),
the single problem decides how much capacity to sell as reserve and how much to trade against the
spread, block by block. By construction it matches or beats every point on the fixed frontier, since
each fixed level is a feasible point of it (`battery/coopt.py`, `make_tier3_coopt.py`,
`plots/tier3_coopt.png`).

| stack over 60 days | perfect foresight | realistic forecast |
|---|---:|---:|
| fixed 500 kW (arbitrage + DC) | GBP 16,606 | GBP 10,020 |
| co-optimized reserve, EFA blocks | GBP 22,966 | GBP 14,412 |

That is about +38% on the perfect-foresight basis and +44% under a realistic forecast, holding a mean
of roughly 715 kW (perfect) to 909 kW (realistic) of reserve rather than a flat 500. The mechanism: a
flat 500 kW both withholds power in the few high-spread hours where arbitrage wanted the full
converter and under-sells availability in the many idle hours where the headroom was free anyway.
Co-optimizing drops the reserve to zero in the peak hours and lifts it toward 1 MW in the idle ones,
so about three quarters of the reserve revenue comes from hours the battery would have sat idle.

Two honest points. The realistic gain is almost all reserve, not better trading: arbitrage actually
falls (GBP 3,704 against the fixed 500's GBP 4,221) while DC nearly doubles to GBP 10,708, because a
weak day-ahead forecast cannot see the spreads but the availability price is forecastable (lag-1
autocorrelation 0.75), so the optimizer rationally tilts toward the predictable revenue. And the
figure uses single-direction (injection) headroom, the same convention as the fixed baseline; a
symmetric DC product, which must absorb and inject, forces the SoC into a middle band and costs about
9% in perfect foresight. Like the rest of Stage 1 the perfect column is a theoretical bound, and the
realistic column still assumes the reserve clears at the published availability price every block.

## Imbalance stacking, and two extensions that did not pay
The dataset's `imbalance_price_gbp_per_mwh` is a second settlement market. Letting each hour settle
discharge at `max(day-ahead, imbalance)` and charge at `min(day-ahead, imbalance)` with perfect
hindsight gives GBP 27,517, a +70% ceiling over the GBP 16,176 day-ahead-only optimum (`bestof_bound`
in `battery/imbalance.py`). That is a labeled upper bound, not a strategy: the settlement choice is
made before the imbalance price is known, and the two prices move together (correlation 0.90). A
leakage-free first step, a persistence forecast of the spread choosing the venue each hour, captures
only GBP 19 of that ceiling over the day-ahead-only realistic run (`run_twoprice_mpc`,
`make_tier_imbalance.py`), so I do not bank it. The spread is real but naive persistence cannot pick
the venue.

I also tested the reviewer reading of the "realistic profit rises with reserve" anomaly as
certainty-equivalent overtrading, replacing the point-forecast MPC with a risk-aware one (a two-stage
stochastic CVaR plan over scenarios drawn from the forecaster's own past errors, `battery/risk_mpc.py`).
It does not recover the lost value; at this scenario width it overcorrects, GBP 1,953 against GBP 4,753
for the point-forecast MPC, so the diagnosis is plausible but the naive cure is worse than the disease.
Both stay as honest negative results, not headline numbers.
