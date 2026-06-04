# Tier 3 Stage 1: frequency response reserve frontier

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

## Limitations
- This is an availability constraint, not yet a live low-frequency dispatch controller.
- The sweep uses perfect foresight to isolate the reserve cost; realistic forecast-based
  operation would sit lower in absolute profit.
- The battery is the original 1 MW / 2 MWh asset. A visible system-frequency impact would
  require scaling to an aggregated fleet or explicitly reporting per-MW impact.
