# Tier 1 decisions log

The two engineering choices the brief flags, plus the supporting assumptions, with
justification. These are the interview talking points: state assumptions plainly.

## AGC PI gains
- Values: Ki = 1.90625, Kp = 1.525.
- How: Ki is derived from a target restoration time, Ki = beta / T_agc, with
  T_agc = 8 s and beta = 15.25 (the system frequency response characteristic of this
  mix). Kp is set as a conservative fraction of the same stiffness, Kp = 0.10 * beta.
- Why: tying both gains to beta avoids arbitrary MW/Hz constants. T_agc = 8 s plus a
  small proportional leg gives recovery at about 21.8 s after the trip, leaving useful
  margin against the 30 s target while keeping overshoot small (about 3.5 mHz above
  nominal in the generated scenario).

## Participation split (flexible-fast)
- CCGT 0.45, Hydro/pumped 0.30, OCGT 0.15, Coal/biomass 0.10. Nuclear, wind, and
  interconnectors are 0. The split sums to 1.
- Why: flexible and fast plant (gas, hydro) leads; baseload nuclear and inverter-based
  wind do not provide secondary response in this snapshot.

## Supporting assumptions
- System base 30 GW; design disturbance 1320 MW. This is used as the Tier 1 design
  loss because it is a standard GB infeed-loss benchmark; larger secured-loss cases
  exist, so this should not be described as the only possible GB largest loss.
- Governor deadband 15 mHz (GB primary response). It is wider than the plus or minus
  10 mHz target, so the final approach is lightly damped, a documented and in-spec
  characteristic rather than a defect.
- High-wind snapshot: system inertia H_sys = 3.45 s, initial RoCoF about 0.32 Hz/s.
- Ramp rates per fuel (percent of own capacity per minute): CCGT 20, OCGT 60, coal 5,
  hydro 150, nuclear 1. Representative values, to be sourced or clearly labelled as
  assumptions in the write-up.
- Anti-windup: back-calculation on the integral state, time constant 25 s.

## Scope and limitations
- Single-area model: no inter-area tie lines, no network power flow, no voltage side.
- One lumped machine per fuel type; linearised around the operating point.
- Parameter values are representative of a GB high-wind dispatch and should be sourced
  against NESO or equivalent published figures.

## Findings worth mentioning
- A first hypothesis that slow coal was the recovery bottleneck was wrong: local
  sweeps suggested the controller tuning, not coal, governed the recovery. Keep the
  sweep evidence if this point is used in the final write-up.
- The proportional term is load-bearing, not cosmetic. A controlled sweep shows that
  tightening T_agc from 10 s to 8 s on its own makes recovery worse (about 32 s, missing
  the 30 s target), because a stronger integral with no added damping rings harder.
  Adding the proportional leg (Kp = 0.10 * beta) cuts overshoot and the late in-band
  wobble by roughly three times and brings recovery to about 21.8 s.
- Why the proportional term works where the integral alone did not: inside the 15 mHz
  governor deadband, primary droop is switched off, so the integral-only loop had no
  damping there and rang. The proportional gain acts on the full frequency error, not the
  deadbanded one, so it supplies exactly that missing damping in the dead zone.
