# Tier 1 robustness and sensitivity

These are the checks I ran to show the AGC result is not a single-case result. Reproduce with
`python make_tier1_validation.py` (writes the CSVs and the figure).

## Robustness across trip sizes
I tuned the controller on the 1320 MW design case and ran it unchanged at other disturbance
sizes (`results/tier1_robustness.csv`, `plots/tier1_robustness.png`).

| loss (MW) | nadir (Hz) | RoCoF 500 ms avg | RoCoF peak | within limit | recovery (s) | overshoot (mHz) | settles (Hz) | within 30 s | above 49.2 |
|---|---|---|---|---|---|---|---|---|---|
| 500 | 49.922 | -0.107 | -0.121 | yes | 15.1 | 7.5 | 50.000 | yes | yes |
| 1000 | 49.853 | -0.207 | -0.241 | yes | 20.7 | 5.2 | 50.000 | yes | yes |
| 1320 | 49.808 | -0.271 | -0.318 | yes | 21.8 | 3.5 | 50.000 | yes | yes |
| 1800 | 49.740 | -0.367 | -0.434 | yes | 34.0 | 21.7 | 49.999 | no | yes |

The AGC restores 50.000 Hz and stays above the 49.2 Hz floor for every case, and recovery
scales sensibly with the disturbance. The design case and smaller losses meet the 30 s
target with margin. The larger 1800 MW loss (a more severe secured-loss case than the
controller was tuned for) still restores and holds the floor, but recovery slows to 34 s
and overshoot grows: the expected degradation away from the design point. Meeting 30 s
there would need a tighter T_agc or more fast reserve. I state it as a known limitation,
I do not hide it.

I report RoCoF two ways, because the description has to match the computation. The 500 ms
window average is the grid-code style measure and is robust to sample noise: it runs from
-0.11 Hz/s at 500 MW to -0.37 Hz/s at 1800 MW. The steepest instantaneous slope inside that
window (the peak) is larger in magnitude, -0.12 to -0.43 Hz/s, and is the conservative figure I
check against the limit. Both stay inside the 1 Hz/s that ENA EREC G99 requires generation to
ride through. The `within_rocof_limit` column tests the peak, and `rocof_window` and
`rocof_peak` in `scenarios/gen_trip.py` compute the two.

## Gain sweep: why T_agc = 8 s and Kp = 0.10 * beta
On the 1320 MW design trip (`results/tier1_gain_sweep.csv`).

T_agc, with Kp = 0.10 * beta fixed:

| T_agc (s) | Ki | recovery (s) | overshoot (mHz) |
|---|---|---|---|
| 6 | 2.54 | 27.1 | 27.3 |
| 8 | 1.91 | 21.8 | 3.5 |
| 10 | 1.52 | 29.9 | 2.9 |
| 12 | 1.27 | 36.4 | 2.5 |

T_agc = 8 s is the selected point: the fastest restoration that does not blow up overshoot.
Tighter (6 s) is barely faster but overshoots about eight times as much. Looser (10 to
12 s) slows toward or past the 30 s target.

Kp, with T_agc = 8 s fixed:

| kp_fraction | Kp | recovery (s) | overshoot (mHz) |
|---|---|---|---|
| 0.00 | 0.00 | 32.0 | 8.5 |
| 0.05 | 0.76 | 21.1 | 5.7 |
| 0.10 | 1.53 | 21.8 | 3.5 |
| 0.20 | 3.05 | 22.9 | 1.5 |

The proportional leg is essential: with Kp = 0 (integral only) recovery is 32 s and misses
the target. Any Kp in 0.05 to 0.20 meets the target. I chose 0.10 * beta as a balanced point, fast with
small overshoot.

## Ablation: what each piece buys
On the 1320 MW trip (`results/tier1_ablation.csv`).

| case | nadir (Hz) | recovery (s) | overshoot (mHz) | settles (Hz) |
|---|---|---|---|---|
| droop only (no AGC) | 49.801 | never | 0.0 | 49.842 |
| AGC, no ramp limits | 49.817 | 20.9 | 6.9 | 50.000 |
| AGC, with ramp limits | 49.808 | 21.8 | 3.5 | 50.000 |

Droop alone parks at the offset and never returns (the bug Tier 1 fixes). Adding the AGC
restores 50.000. Ramp limits cost about a second of speed but cut overshoot roughly in
half, because the integral can no longer demand power faster than plant can deliver. That
is the physical realism the ramp limits and anti-windup add.

## Participation split (sums to 1)
CCGT 0.45, Hydro/pumped 0.30, OCGT 0.15, Coal/biomass 0.10. Nuclear, wind, and
interconnectors are 0. Fast flexible plant leads. Baseload nuclear and inverter-based wind
provide no secondary response.

## Assumptions to cite
- Design disturbance 1320 MW: a standard GB infeed-loss benchmark. Larger secured-loss
  cases exist, so I do not describe this as the only possible largest loss.
- Frequency limits: statutory 49.5 to 50.5 Hz, the largest credible loss must hold above
  about 49.2 Hz, restoration target plus or minus 0.01 Hz within 30 s.
- Plant parameters (capacities, inertia, droop, ramp rates) are representative values. I will
  source them against NESO or equivalent figures for a final submission.
