# Grid-Aware Battery Optimisation

Working toward a grid-aware battery optimisation project for the Piclo engineering
challenge. The current repo completes Tier 1: fixing the grid-frequency simulator's
secondary frequency restoration.

## The three tiers

- **Tier 1 (physics).** Add proper secondary frequency control (AGC) to the grid
  model, so frequency returns to 50.000 Hz after a disturbance instead of parking
  at the droop offset.
- **Tier 2 (markets).** Replace the perfect-foresight battery LP with a rolling
  horizon MPC that acts on a price forecast. Planned next.
- **Tier 3 (coupling).** Let the battery's market behaviour respond to grid
  frequency state through a supervisory controller. Planned after Tier 2.

## Structure

| path | purpose |
|------|---------|
| `gridsim/` | frequency model and AGC secondary control (Tier 1) |
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
Tiers 2 and 3 are not implemented yet.

Regenerate the Tier 1 results:

```
python make_tier1_figures.py
```

Run the tests:

```
pytest
```
