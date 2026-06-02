# Tier 1 decisions log

The two engineering choices the brief flags, plus the supporting assumptions, with
justification. These are the interview talking points: state assumptions plainly.

## AGC integral gain Ki
- Value: Ki = 1.525.
- How: derived from a target restoration time, Ki = beta / T_agc, with T_agc = 10 s and
  beta = 15.25 (the system frequency response characteristic of this mix).
- Why: secondary response acts over tens of seconds; tying the gain to a restoration
  time and the system beta avoids a magic number. T_agc = 10 s lands recovery at about
  28 s, just inside the 30 s target. A shorter T_agc would add margin at the cost of
  more actuator stress.

## Participation split (flexible-fast)
- CCGT 0.45, Hydro/pumped 0.30, OCGT 0.15, Coal/biomass 0.10. Nuclear, wind, and
  interconnectors are 0. The split sums to 1.
- Why: flexible and fast plant (gas, hydro) leads; baseload nuclear and inverter-based
  wind do not provide secondary response in this snapshot.

## Supporting assumptions
- System base 30 GW; design disturbance 1320 MW (GB largest credible single loss).
- Governor deadband 15 mHz (GB primary response). It is wider than the plus or minus
  10 mHz target, so the final approach is lightly damped, a documented and in-spec
  characteristic rather than a defect.
- High-wind snapshot: system inertia H_sys = 3.45 s, initial RoCoF about 0.32 Hz/s.
- Ramp rates per fuel (percent of own capacity per minute): CCGT 20, OCGT 60, coal 5,
  hydro 150, nuclear 1. Representative values, to be sourced in the write-up.
- Anti-windup: back-calculation, time constant 25 s.

## Scope and limitations
- Single-area model: no inter-area tie lines, no network power flow, no voltage side.
- One lumped machine per fuel type; linearised around the operating point.
- Parameter values are representative of a GB high-wind dispatch and should be sourced
  against NESO or equivalent published figures.

## Findings worth mentioning
- A first hypothesis that slow coal was the recovery bottleneck was wrong: a parameter
  sweep showed the controller tuning, not coal, governed the recovery. Validate, do not
  assume.
- The deadband being wider than the restoration target removes primary damping near 50,
  so the secondary loop must settle on its own; this is why the recovery shows a small
  in-band wobble.
