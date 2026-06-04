# Tier 2: rolling-horizon MPC for the battery

## Problem
The EGS arbitrage LP optimises all 1440 hours at once with perfect knowledge of every
future price. That perfect foresight is an upper bound, not a strategy, because no
operator knows future prices. Tier 2 replaces it with a realistic rolling-horizon MPC.

## Approach (MPC)
Each hour: forecast the next 24 h of prices, solve the arbitrage LP over that window from
the battery's real state of charge, commit only the first hour's action, book that
action's profit at the REAL price, carry the real state of charge forward, and roll on.
The same optimiser (`battery/arbitrage.py`) serves both the perfect foresight baseline
(one call over all prices) and the MPC (a call per hour).

## Decisions (set and justified by the author)
- **Forecast:** same-hour trailing average. Each future hour is forecast as the average
  of that hour-of-day over the last 7 complete days. Steadier than naive persistence, and
  it uses only past data.
- **End-of-window handling:** a terminal value on leftover energy, priced at the window's
  mean forecast price, intended to stop a finite window dumping its charge at the edge.
  (The ablation below shows this risk does not actually bite on this dataset; the value is
  kept as a standard, near-free safeguard.)
- **State-of-charge continuity:** the real charge is carried forward each hour, so each
  plan starts from where the battery actually is.

## Validation
- The perfect-window MPC (true prices within each 24 h window) reproduces the full
  perfect foresight LP to within about 0.1%, which validates the rolling-horizon
  implementation on this dataset and shows that the main loss in the realistic MPC runs
  is forecast quality, not the 24 h receding-horizon machinery or the terminal value.
- No future leakage: a test corrupts every price from hour h onward and confirms the
  realistic forecasts do not change. The terminal value uses the forecast-window mean,
  never the future price series. (`perfect_window` and the noise probe use the future on
  purpose and are clearly labelled as analysis tools, not forecasts.)

## Terminal-value ablation
Does the terminal value earn its place? Running the perfect-window MPC (perfect prices, so
the terminal value is isolated from forecast error) with and without it, across window
lengths (`make_tier2_ablation.py`, `results/tier2_terminal_ablation.csv`):

| window | terminal on | terminal off | difference |
|---|---|---|---|
| 24 h | GBP 16,155 | GBP 16,194 | -39 (-0.2%) |
| 12 h | GBP 16,155 | GBP 16,194 | -39 (-0.2%) |
| 6 h | GBP 16,101 | GBP 16,181 | -80 (-0.5%) |

The terminal value is near-neutral at every horizon, even 6 h, and marginally
counterproductive. So the horizon-edge dumping the brief warned about does not bite on
this dataset, for three reasons: a 24 h window already spans the daily arbitrage cycle;
valuing leftover energy at the window mean is near-neutral by construction (the battery is
roughly indifferent between holding energy worth the mean and selling at the mean); and
only the first hour is committed each step, so the window's end bias is washed out before
it reaches a committed action. The value is kept as a standard, near-free safeguard, but
the honest conclusion is that it is not load-bearing here.

## Result
- Perfect foresight: GBP 16,176 over 60 days.
- MPC with simple realistic forecasts: GBP 3,056 (persistence) to GBP 3,927 (same-hour
  average), about 19 to 24% of perfect foresight. Price uncertainty destroys roughly
  three quarters of the achievable arbitrage value on this dataset.
- Bonus, the value of forecast quality: a synthetic forecast (true prices plus zero-mean
  Gaussian noise that grows with lead time) gives a smooth profit-versus-error curve,
  100% at zero noise falling to about 20% at sigma = 80 GBP/MWh. The simple forecasts sit
  at the noisy end of that curve, so these day-ahead prices are genuinely hard to forecast
  from history and better forecasting carries large value.

## Headline
A 24-hour rolling MPC with perfect within-window prices nearly matches the full
perfect foresight LP, so the rolling implementation is sound. With simple realistic
forecasts, profit falls to 19 to 24% of perfect foresight, quantifying the value
destroyed by price uncertainty.

## Scope and limitations
- Day-ahead arbitrage only; the reserve and imbalance market stacks from the EGS model
  are not yet wired into the MPC.
- Forecasts are deliberately simple, as the brief asks; a better forecast would capture
  more, which the forecast-error sweep quantifies.
- The terminal value uses the window mean as a proxy for the marginal value of stored
  energy; a more careful value function is possible.
- Each MPC solves about 1440 small LPs via CBC subprocesses, so a full run takes tens of
  seconds; fine for analysis, not for real-time use as written.
