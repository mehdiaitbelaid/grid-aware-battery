# Tier 1 design: secondary frequency control (AGC)

## Objective
After a disturbance the grid model settles at a droop-determined frequency offset
and never returns to 50.000 Hz. Tier 1 adds proper secondary control so that
frequency returns to within plus or minus 0.01 Hz of 50.000 within 30 s of the
generation trip. The trip is modelled as a sustained loss, so there is no separate
"disturbance end" instant in this Tier 1 scenario.

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
- Participation factors summing to 1: high for gas and hydro, zero for nuclear,
  wind, and interconnectors in this Tier 1 snapshot. BESS participation is deferred
  to the battery-coupling tiers.
- Ramp-rate limits per fuel type, applied to the secondary (AGC) dispatch rather
  than to the fast primary response (which is limited by the governor time constant).
- PI-based AGC on the area control error (here just the frequency error), in addition
  to primary droop. The proportional term improves transient recovery; the integral
  term removes the droop offset.

## The controller
The secondary command is a PI correction on the area control error, allocated across
units by participation factor and rate-limited by each unit's ramp capability.
Back-calculation anti-windup compares the total ramp-limited dispatch with the full
PI command and restrains the integral state when the slow actuators lag. The gains
are derived from system stiffness rather than hand-tuned:

    Ki = beta / T_agc
    Kp = kp_fraction * beta

where beta is the system frequency response characteristic. In the multi-unit model:

    beta = D + sum_i (MW_i / MW_base) / R_i

over generators that provide primary droop response. `T_agc` is the chosen secondary
restoration time constant; `kp_fraction` sets how much immediate secondary response
is added before the integral catches up.

## Judgement calls (set and justified by the author)
- **Ki and Kp**, via the target restoration time T_agc and proportional fraction of
  beta.
- **The participation split** across fuel types (sums to 1).

## Validation targets
- Baseline (droop only) settles at the droop offset and does not return.
- With AGC: frequency back within plus or minus 0.01 Hz of 50.000 within 30 s of
  the trip.
- Nadir and rate of change of frequency physically reasonable; frequency holds above
  roughly 49.2 Hz for the design disturbance.

## Deliverables
- A generator-trip scenario.
- A before and after CSV: baseline droop only versus fixed AGC.
- Frequency recovery plots.
- Unit tests (restoration, 30 s recovery target, gain scaling, participation sums,
  droop offset, multi-unit aggregation, and anti-windup overshoot bound).

## Build order
1. Scaffold and baseline RK4 model.
2. Per-unit and Hz scaling, validate the offset against the formula.
3. Multi-unit GB mix.
4. Governor deadband.
5. AGC: PI plus participation, with ramp limits and anti-windup on the secondary
   dispatch; set Ki and Kp.
6. Gen-trip scenario and before and after CSV.
7. Recovery plots.
8. Tests.
