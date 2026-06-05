# Grid-Aware Battery Optimisation

This repo is my Piclo engineering challenge submission. It covers all three tiers. Tier 1
fixes the grid frequency simulator's secondary frequency restoration. Tier 2 replaces the
battery's perfect foresight optimiser with a rolling-horizon MPC. Tier 3 couples the two
through a reserve, a physical fleet response, and a supervisor.

## The three tiers

- **Tier 1 (physics).** I added proper secondary frequency control (AGC) to the grid
  model, so frequency returns to 50.000 Hz after a disturbance instead of parking
  at the droop offset.
- **Tier 2 (markets).** I replaced the perfect foresight battery LP with a rolling
  horizon MPC that acts on a price forecast.
- **Tier 3 (coupling).** I let the battery's market behaviour respond to grid
  frequency state through a supervisory controller. I added Stages 1, 2, and 3: the reserve
  arbitrage frontier, the battery's physical frequency response in the grid model, and the
  supervisor that switches between them on the live frequency.

## Structure

| path | purpose |
|------|---------|
| `gridsim/` | frequency model and AGC secondary control (Tier 1) |
| `battery/` | arbitrage LP and rolling-horizon MPC (Tier 2) |
| `data/` | the 60-day GB hourly price series |
| `scenarios/` | disturbance and market scenario definitions |
| `results/` | exported CSVs |
| `plots/` | before and after figures |
| `tests/` | unit tests |
| `docs/` | design notes |
| `DECISIONS.md` | the headline modelling trade-offs, in one place |

## Frequency model provenance

I reimplemented the Tier 1 frequency model from my BEng dissertation grid
stability simulator (`grid-stability-sim`), which used a JavaScript single-area
swing-equation model with droop and an ad hoc AGC integral term. I kept the
single-area frequency dynamics but packaged them as importable, testable Python and
added a structured secondary controller with participation factors, ramp limits, and
anti-windup.

## Running

```
pip install -r requirements.txt
```

I add per-tier entry points and tests as each tier lands.

## Status

Tier 1 is complete. The PI-based AGC secondary control returns frequency to within plus or
minus 0.01 Hz of 50.000 Hz in 21.8 s after a sustained 1320 MW generation trip. The
default 60 s artifact ends at 49.99999 Hz. See
`plots/tier1_recovery.png`, `results/tier1_gen_trip.csv`, and `docs/decisions.md`.

Tier 2 is complete. A 24-hour rolling MPC with perfect within-window prices nearly matches
the full perfect foresight LP, within about 0.1%, which checks the rolling-horizon
implementation on this dataset. With simple realistic forecasts profit falls to 19 to 29% of perfect
foresight, which quantifies the value destroyed by price uncertainty. A terminal-value
ablation confirms the end-of-window guardrail is near-neutral on this dataset, within 0.5%
across the 24, 12, and 6 hour windows, so I keep it as a standard safeguard rather than a
profit driver. See `plots/tier2_decomposition.png`, `plots/tier2_forecast_value.png`,
`results/tier2_mpc.csv`, `results/tier2_terminal_ablation.csv`, and `docs/tier2.md`.

In Tier 3 Stage 1 I ran a reserve study. Sweeping reserved upward response from 0 to 1000 kW
traces the profit against availability frontier, where reserving 500 kW for 30 minutes
keeps about 67% of perfect foresight arbitrage. A forecast sensitivity check shows that
cost is an upper bound: under this simple forecast the reserve costs little, because a
weak forecast was not using the held back capacity anyway.

In Tier 3 Stage 2 I put the reserved power into the frequency model as an aggregated fleet with
synthetic droop and synthetic inertia. On the severe 1800 MW trip that Tier 1 missed the
30 s target on, a 500 MW fleet restores within target (34 to 22.9 s), while too large a
fleet over-helps the dip and drags the settle. See `docs/tier3.md`,
`plots/tier3_pareto.png`, and `plots/tier3_stage2_severe.png`.

In Tier 3 Stage 3 I built the supervisor: a four-mode state machine (ARBITRAGE, RESERVE, RESPONSE,
RECOVERY) with hysteresis that switches the battery between arbitrage and frequency response
on the live frequency, and tapers the response during recovery to protect the settle. On a
severe 1800 MW trip it cancels charging, supports the grid, then returns to arbitrage with no
chatter. See `coupling/`, `docs/tier3.md`, and `plots/tier3_stage3_timeline.png`.

I added three runs to round out the physics: the symmetric fleet contains an over-frequency
surplus (`plots/tier3_overfreq.png`), a ramp-rate sweep shows response speed is a second axis
beyond reserved power (`plots/tier3_speed.png`), and sweeping reserve and speed together maps
the nadir surface, where you need both (`plots/tier3_surface.png`).

I also priced whether it pays, using the DC availability price in the dataset
(`ancillary_availability_gbp_per_mw_per_h`, mean GBP 8.06/MW/h, above the GBP 7.46/MW/h break-even).
The 500 kW earns GBP 5,800 over 60 days, which nets GBP +431 against the perfect-foresight cost of
reserving, and is almost all net under a realistic forecast where the reserve costs about nothing
(`plots/tier3_value.png`). On this data it pays. The 500 kW stands for part of an aggregated fleet,
since DC offers are at least 1 MW.

A degradation sensitivity prices battery wear as a throughput cost and sweeps it: at a central
GBP 10 per MWh the break even falls from GBP 7.46 to GBP 6.65/MW/h, because arbitrage cycles
hard while the reserve sits idle, so pricing wear strengthens the response case
(`plots/tier3_degradation.png`).

Regenerate the results:

```bash
# Tier 1
python make_tier1_figures.py      # before and after recovery plot
python make_tier1_validation.py   # robustness sweep across trip sizes

# Tier 2
python make_tier2_figures.py      # MPC against perfect foresight, plus the forecast-error value
python make_tier2_ablation.py     # terminal-value ablation, the honest null result

# Tier 3
python make_tier3_pareto.py       # reserve vs arbitrage frontier (perfect foresight)
python make_tier3_sensitivity.py  # the same frontier under a realistic forecast
python make_tier3_value.py        # DC break-even, the punchline (uses the sensitivity csv above)
python make_tier3_degradation.py  # how battery wear shifts the reserve break even
python make_tier3_stage2_sweep.py # what the reserve buys inside the frequency model
python make_tier3_stage3.py       # the supervisor event timeline, with SoC tracking
python make_tier3_supervisor_sweep.py  # supervisor threshold sweep, a second design axis
python make_tier3_overfreq.py     # symmetric over-frequency containment
python make_tier3_speed.py        # response speed as a second axis
python make_tier3_surface.py      # nadir over reserve by speed
```

Run the tests:

```
pytest
```
