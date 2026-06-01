# Tier 1 design: secondary frequency control (AGC)

## Objective
After a disturbance the grid model settles at a droop-determined frequency offset
and never returns to 50.000 Hz. Tier 1 adds proper secondary control so that
frequency returns to within plus or minus 0.01 Hz of 50.000 within 30 s of the
disturbance ending.

## Model
A single-area, multi-unit load frequency control (LFC) model:

- one system frequency (single area, single bus),
- several lumped generators by fuel type, each with inertia H, droop R, a
  governor/turbine time constant, a ramp-rate limit, and an AGC participation factor,
- a per-unit formulation with a stated base power, with frequency reported in Hz.

This captures everything relevant to frequency restoration and AGC behaviour without
modelling the network, voltage, or reactive power.

### Scope and assumptions (stated plainly)
- Single area: no inter-area tie lines and no network power flow.
- One lumped machine per fuel type, not individual units.
- Active-power frequency dynamics only: no voltage or reactive side.
- Linearised around the operating point (the standard LFC assumption).

## Realism features
- A realistic GB generation mix with representative capacities, inertia, droop, and
  ramp rates.
- Per-unit base power and correct Hz scaling, so a credible loss moves frequency by
  tenths of a Hz and grid-code magnitudes appear (statutory band 49.5 to 50.5 Hz;
  the largest credible loss must hold above roughly 49.2 Hz).
- A governor deadband (about plus or minus 15 mHz) so governors ignore tiny wobble.
- Participation factors summing to 1: high for gas, hydro, and BESS, near zero for
  nuclear.
- Ramp-rate limits per fuel type.
- AGC as a PI loop on the area control error (here just the frequency error) with
  anti-windup and a realistic update interval.

## The controller
The secondary command is an integral of the area control error, allocated across
units by participation factor, clipped to each unit's ramp limit, with anti-windup
that halts integration while any actuator is saturated. The gain is derived from a
target restoration time rather than hand-tuned:

    Ki = beta / T_agc,   where beta = 1/R + D is the system frequency response
    characteristic (power per Hz) and T_agc is the chosen restoration time constant.

## Judgement calls (set and justified by the author)
- **Ki**, via the target restoration time T_agc (order of tens of seconds).
- **The participation split** across fuel types (sums to 1).

## Validation targets
- Baseline (droop only) settles at the droop offset and does not return.
- With AGC: frequency back within plus or minus 0.01 Hz of 50.000 within 30 s.
- Nadir and rate of change of frequency physically reasonable; frequency holds above
  roughly 49.2 Hz for the design disturbance.

## Deliverables
- A generator-trip scenario.
- A before and after CSV: baseline droop only versus fixed AGC.
- Frequency recovery plots.
- Unit tests (restoration, participation sums, anti-windup, energy balance).

## Build order
1. Scaffold and baseline RK4 model.
2. Per-unit and Hz scaling, validate the offset against the formula.
3. Multi-unit GB mix.
4. Ramp limits and governor deadband.
5. AGC: PI plus participation plus anti-windup, set Ki.
6. Gen-trip scenario and before and after CSV.
7. Recovery plots.
8. Tests.
