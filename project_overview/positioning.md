# TICK Positioning

Last reviewed: 2026-07-31

## Core Position

TICK is a discovery-first trading terminal that finds markets worth watching
now, explains the shape of their movement, and routes execution across venues.

The long-term ambition is to build the best day-trading perpetuals product.
The differentiated external claim should remain narrower and provable:

> TICK finds what is moving, explains how it is moving, and makes that market
> executable through one coherent trading experience.

Venue aggregation is infrastructure. TICK Engine and the product experience
built around it are the primary product advantage.

## TICK Engine

TICK Engine is the shared server-side discovery and interpretation layer. It
continuously scans markets for short-horizon activity, interprets the shape and
freshness of that movement, measures it against real execution conditions, and
surfaces the markets most suited to active trading.

It does not predict direction or tell a user which side to take. It explains
what the market is doing and whether the observed movement can be executed
effectively.

The engine must produce four separate judgments:

| Judgment | Question |
| --- | --- |
| `ACTIVE` | Is movement unusual relative to this market's normal behavior? |
| `SHAPE` | Is movement impulsive, oscillating, compressing, expanding, reversing, or cooling? |
| `TRADEABLE` | Is movement meaningful relative to fees, spread, impact, liquidity, and execution latency? |
| `AVAILABLE` | Can this user execute it now with the selected preset, wallet, market, and venue route? |

Raw volatility alone is insufficient. The most volatile market may be stale,
expensive, illiquid, already exhausted, or unavailable to the user.

Useful product states may include:

```text
IMPULSE BUILDING
RANGE EXPANDING
FAST OSCILLATION
BREAKOUT COOLING
NEAR 1H LOW
COST COVERED
ROUTE DEGRADED
WAIT
```

These states describe recent observations. They are not long or short signals.

## Market Regimes

The first Engine model should organize short-horizon behavior around two broad
regimes.

### Directional

Directional markets show an impulse, breakout, or persistent displacement.
A trader may interpret this behavior as a possible short continuation scalp.

The interface can emphasize:

- directional efficiency;
- impulse age and freshness;
- acceleration or cooling;
- range breaks;
- participation where real data is available.

### Oscillating

Oscillating markets show repeated swings, reversals, or movement inside a
short-term range. A trader may interpret this behavior around recent extremes.

The interface can emphasize:

- swing amplitude and frequency;
- recent range position;
- reversal count;
- range stability;
- movement relative to executable cost.

Neither regime predicts what happens next. A directional move can reverse, and
an observed range can break.

## Defensibility

TICK Engine becomes defensible through its retained observations and measured
feedback loop rather than one isolated formula.

For every surfaced state, retain:

```text
signal timestamp and Engine version
observed movement shape
market and route conditions
estimated cost and measured execution latency
subsequent 10s, 30s, 60s, and 5m movement
maximum favorable and adverse excursion
time until movement covered estimated cost
signal lifetime
executable fill and final route outcome
```

This dataset should establish which market states remain meaningful after real
latency and costs. Pulse should be evaluated against random and simple
volatility-ranking baselines before predictive language is used.

## Product Surfaces

TICK should remain one system expressed through several surfaces.

### Mobile

The mobile product compresses the loop:

```text
find one active market
understand its current shape
open with a visible preset
watch net exposure and risk
close and understand the result
```

### Web

The web product offers deeper comparison and context for active day traders:

- compare Engine-ranked opportunities;
- inspect several time horizons;
- understand movement shape and signal age;
- compare route economics and execution quality;
- manage positions and review previous signals.

It should not become a generic TradingView clone. Pulse, market interpretation,
route quality, and financially explainable execution should remain dominant.

### API

The API direction should be split into two products.

`TICK Engine API` exposes normalized market states, rankings, movement shape,
tradeability, route quality, and historical evaluation.

`TICK Execution API` exposes quotes, opening, closing, positions,
reconciliation, and venue routing through normalized trading primitives.

The Engine API can become paid market infrastructure. The execution API can
support automated traders, partners, and points participants after its
authentication, limits, idempotency, and transaction-recovery model is ready
for programmatic traffic.

## Venue Strategy

Users should receive execution quality rather than a visible list of venues.
TICK Router should compare routes using:

```text
effective fill
round-trip cost
execution latency
market and leverage availability
liquidity and price impact
route reliability
position and order capabilities
```

Discovery data may come from broader sources than the execution venue. Final
quotes, liquidation, stops, fills, and PnL must use the selected route's own
rules and price inputs.

## Community Position

TICK needs credibility with active traders. A respected trader or operator who
is connected to day-trading communities can help shape the product, explain it,
and create a direct feedback loop with users.

That role should be supported by evidence from Engine evaluation and execution
history. The product should earn trust through clear observations, honest
costs, and repeatable execution rather than directional claims.

## Product Discipline

The interface can be visually alive and data-rich, but it should improve
attention and comprehension rather than manufacture reasons to trade.

TICK must help users recognize both when a market deserves attention and when
the correct state is `WAIT`. A product that encourages action from raw movement
alone will eventually lose user trust to fees, poor execution, and exhausted
signals.

