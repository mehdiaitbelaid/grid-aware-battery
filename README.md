# Grid-Aware Battery Optimisation

Connecting a grid frequency simulator to a battery arbitrage optimiser, so that
market decisions respect physical grid limits and physical limits inform market
behaviour. Built for the Piclo engineering challenge.

## The three tiers

- **Tier 1 (physics).** Add proper secondary frequency control (AGC) to the grid
  model, so frequency returns to 50.000 Hz after a disturbance instead of parking
  at the droop offset.
- **Tier 2 (markets).** Replace the perfect-foresight battery LP with a rolling
  horizon MPC that acts on a price forecast.
- **Tier 3 (coupling).** Let the battery's market behaviour respond to grid
  frequency state through a supervisory controller.

## Structure

| path | purpose |
|------|---------|
| `gridsim/` | frequency model and AGC secondary control (Tier 1) |
| `battery/` | arbitrage LP and rolling horizon MPC (Tier 2, added later) |
| `coupling/` | supervisor linking the MPC and the grid sim (Tier 3, added later) |
| `scenarios/` | disturbance and market scenario definitions |
| `results/` | exported CSVs |
| `plots/` | before and after figures |
| `tests/` | unit tests |
| `docs/` | design notes |

## Frequency model provenance

The frequency model originates from the author's BEng dissertation grid stability
simulator (a JavaScript single-area swing-equation sim). It is reimplemented here
as an importable, testable Python module and extended with proper secondary control.

## Running

```
pip install -r requirements.txt
```

Per-tier entry points and tests are added as each tier lands.

## Status

Tier 1 in progress.
