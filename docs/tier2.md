# Tier 2: rolling-horizon MPC for the battery

## Problem
The EGS arbitrage LP optimises all 1440 hours at once with perfect knowledge of every
future price. That perfect foresight is an upper bound, not a strategy, because no
operator knows future prices. For Tier 2 I replaced it with a realistic rolling-horizon MPC.

## Approach (MPC)
Each hour I do this: forecast the next 24 h of prices, solve the arbitrage LP over that window from
the battery's real state of charge, commit only the first hour's action, book that
action's profit at the REAL price, carry the real state of charge forward, and roll on.
The same optimiser (`battery/arbitrage.py`) serves both the perfect foresight baseline
(one call over all prices) and the MPC (a call per hour).

## Decisions (mine to set and justify)
- **Forecast:** same-hour trailing average. I forecast each future hour as the average
  of that hour-of-day over the last 7 complete days. It is steadier than naive persistence, and
  it uses only past data.
- **End-of-window handling:** a terminal value on leftover energy, priced at the window's
  mean forecast price, meant to stop a finite window dumping its charge at the edge.
  (The ablation below shows this risk does not actually bite on this dataset. I keep the
  value as a standard inventory guardrail.)
- **State-of-charge continuity:** I carry the real charge forward each hour, so each
  plan starts from where the battery actually is.

## Validation
- The perfect-window MPC (true prices within each 24 h window) reproduces the full
  perfect foresight LP to within about 0.1%, which checks the rolling-horizon
  implementation on this dataset and suggests that the main loss in the realistic MPC runs
  is forecast quality, not the 24 h receding-horizon machinery or the terminal value.
- No future leakage: a test corrupts every price from hour h onward and confirms the
  realistic forecasts do not change. The terminal value uses the forecast-window mean,
  never the future price series. (`perfect_window` and the noise probe use the future on
  purpose and I label them as analysis tools, not forecasts.)

## Terminal-value ablation
Does the terminal value earn its place? I ran the perfect-window MPC (perfect prices, so
the terminal value is isolated from forecast error) with and without it, across window
lengths (`make_tier2_ablation.py`, `results/tier2_terminal_ablation.csv`):

| window | terminal on | terminal off | difference |
|---|---|---|---|
| 24 h | GBP 16,155 | GBP 16,194 | -39 (-0.2%) |
| 12 h | GBP 16,155 | GBP 16,194 | -39 (-0.2%) |
| 6 h | GBP 16,101 | GBP 16,181 | -80 (-0.5%) |

The cash impact of the terminal value is small at every horizon, within 0.5%. I have to read this
with final inventory in mind: the terminal-off runs can end with less stored energy,
which flatters their cash, so the small terminal-off advantage is partly an inventory effect
rather than a real edge (see the final-SoC fairness note under Result). The mechanics that
keep the horizon-edge bias small here still hold: a 24 h window already spans the daily
arbitrage cycle, and only the first hour is committed each step, so the window's end bias is
washed out before it reaches a committed action. I keep the terminal value as a standard,
inventory guardrail.

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
- Final-inventory fairness: the perfect foresight baseline is forced to end at its starting
  charge (1000 kWh), but the realistic MPCs end where they land. The same-hour run ends near
  empty (128 kWh) and persistence ends empty (0 kWh), so their cash slightly overstates them,
  because they sold stored energy they never replaced. When I credit the end-of-horizon inventory
  at the mean price, the adjusted profits are GBP 3,880 (same-hour) and GBP 3,002
  (persistence), about GBP 50 below cash, so the 19 to 24% comparison changes little. The perfect-window
  MPC ends fuller (1876 kWh), so its cash is if anything understated. `results/tier2_mpc.csv`
  now carries `final_soc_kwh` and `adj_profit_gbp` for every run.

## Headline
A 24-hour rolling MPC with perfect within-window prices nearly matches the full
perfect foresight LP, so the rolling implementation passes this dataset check. With simple realistic
forecasts, profit falls to 19 to 24% of perfect foresight, which quantifies the value
destroyed by price uncertainty.

## Scope and limitations
- Day-ahead arbitrage only. I have not yet wired the reserve and imbalance market stacks
  from the EGS model into the MPC.
- Forecasts are deliberately simple, as the brief asks. A better forecast would capture
  more, which the forecast-error sweep quantifies.
- The terminal value uses the window mean as a proxy for the marginal value of stored
  energy. A more careful value function is possible.
- Each MPC solves about 1440 small LPs via CBC subprocesses, so a full run takes tens of
  seconds. Fine for analysis, not for real-time use as written.
