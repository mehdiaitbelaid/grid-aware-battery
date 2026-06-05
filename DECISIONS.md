# Key modelling decisions

The headline simplifications behind this project, in one place. Each is a deliberate
assumption with its reason. The rule throughout: state the assumption plainly, because an
honest simplification is worth more than a model that pretends at detail its inputs cannot
support. Per-tier detail lives in `docs/decisions.md` (Tier 1), `docs/tier2.md` (Tier 2),
and `docs/tier3.md` (Tier 3).

## Single-area grid, no network
I model the system as one bus: a single swing equation for system frequency, with one
lumped machine per fuel type. There are no transmission lines, no bus voltages, no
inter-area flows. The brief's questions are system-frequency questions: how deep the nadir
goes, how fast frequency falls, how long restoration takes. A single-area model answers
those honestly. A full network model would add buses and line flows that do not change the
frequency story on a single connected system, while implying a spatial accuracy the inputs
do not justify. The cost is real and stated: no inter-area oscillations, no locational
effects. See `docs/decisions.md`.

## Hourly market resolution
Arbitrage is solved on the hourly day-ahead price series the challenge provides. I do not
synthesise sub-hourly prices or model within-hour balancing. The data is hourly, so hourly
is the resolution the inputs actually support. Faster markets (imbalance, sub-hourly
dispatch) are real revenue, but inventing a finer time grid would be fabricating signal that
is not in the data. The forecast-error sweep in Tier 2 shows how much the result depends on
price quality, which is the honest way to flag this. See `docs/tier2.md`.

## First-order fleet response, not a full inverter model
The battery fleet supports frequency two ways: synthetic droop (inject power proportional to
the frequency drop, capped at the reserve) and synthetic inertia (an added effective inertia
term that slows the initial RoCoF). Both enter the swing equation as clean terms. Those two
terms capture what a battery actually does to system frequency: lift the nadir and slow the
fall. A full power-electronics model would add converter dynamics and a df/dt filter that
shift the numbers slightly but not the story. I label it a first-order approximation and note
that a real inverter must filter a noisy df/dt measurement. See `docs/tier3.md`.

## Provided price series, used as given
I treat the supplied hourly price series as the market rather than sourcing live data, for
reproducibility: anyone cloning the repo runs the same numbers. The point of the work is the
method (rolling MPC, reserve frontier, the coupling), not a claim about any particular
trading day. Forecast quality, which a live series would also need, is studied separately
through the same-hour-average forecast and the noise sweep. See `docs/tier2.md`.

## Perfect foresight is a yardstick, not a strategy
Where I use perfect foresight (the arbitrage upper bound, the reserve frontier), it is a
ceiling to measure against, never a claim of operational performance. The realistic rolling
MPC is the strategy; perfect foresight only tells me how much room is left between it and the
best possible. Reporting both is what makes the forecast-cost number mean something. See
`docs/tier2.md` and `docs/tier3.md`.
