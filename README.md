# Grid-Aware Battery Optimisation

Working toward a grid-aware battery optimisation project for the Piclo engineering
challenge. The current repo completes Tiers 1 and 2: fixing the grid-frequency
simulator's secondary frequency restoration, and replacing the battery's
perfect foresight optimiser with a rolling-horizon MPC.

## The three tiers

- **Tier 1 (physics).** Add proper secondary frequency control (AGC) to the grid
  model, so frequency returns to 50.000 Hz after a disturbance instead of parking
  at the droop offset.
- **Tier 2 (markets).** Replace the perfect foresight battery LP with a rolling
  horizon MPC that acts on a price forecast. Done.
- **Tier 3 (coupling).** Let the battery's market behaviour respond to grid
  frequency state through a supervisory controller. Stage 1 added: reserve-constrained
  arbitrage frontier; full frequency-state supervisor still to follow.

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

## Frequency model provenance

The Tier 1 frequency model is reimplemented from the author's BEng dissertation grid
stability simulator (`grid-stability-sim`), which used a JavaScript single-area
swing-equation model with droop and an ad hoc AGC integral term. This repo keeps the
single-area frequency dynamics but packages them as importable, testable Python and
adds a structured secondary controller with participation factors, ramp limits, and
anti-windup.

## Running

```
pip install -r requirements.txt
```

Per-tier entry points and tests are added as each tier lands.

## Status

Tier 1 complete. PI-based AGC secondary control returns frequency to within plus or
minus 0.01 Hz of 50.000 Hz in 21.8 s after a sustained 1320 MW generation trip. The
default 60 s artifact ends at 49.99999 Hz. See
`plots/tier1_recovery.png`, `results/tier1_gen_trip.csv`, and `docs/decisions.md`.

Tier 2 complete. A 24-hour rolling MPC with perfect within-window prices nearly matches
the full perfect foresight LP (within about 0.1%), validating the rolling-horizon
implementation; with simple realistic forecasts profit falls to 19 to 24% of perfect
foresight, quantifying the value destroyed by price uncertainty. See
`plots/tier2_decomposition.png`, `plots/tier2_forecast_value.png`, `results/tier2_mpc.csv`,
and `docs/tier2.md`.

Tier 3 Stage 1 is implemented as a reserve-constrained arbitrage study. Sweeping reserved
upward response from 0 to 1000 kW traces the profit-vs-availability frontier: reserving
500 kW for 30 minutes keeps about 67% of perfect foresight arbitrage profit. See
`plots/tier3_pareto.png`, `results/tier3_pareto.csv`, and `docs/tier3.md`. The remaining
Tier 3 work is the live frequency-state supervisor and physical grid-response coupling.

Regenerate the results:

```
python make_tier1_figures.py
python make_tier2_figures.py
python make_tier3_pareto.py
```

Run the tests:

```
pytest
```
