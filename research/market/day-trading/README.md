# Day Trading and Cross-Asset Research

Last reviewed: 2026-07-30

## Research Question

How should TICK help a person find and act on short-lived market movement
without becoming a dense professional terminal, hiding trading costs, or using
design mechanics whose main effect is more trading?

## Working Answer

TICK should compress five jobs:

```text
scan many markets
-> explain why one is active now
-> show enough context to orient the trader
-> execute one visible risk preset
-> explain the real net result
```

Crypto is the first live execution rail, not the permanent product boundary.
The durable product is a cross-asset volatility scanner and normalized
execution loop spanning crypto, FX, indices, commodities, equities, and
eventually liquid rates products when supported routes and user eligibility
permit them.

The scanner must keep three ideas separate:

```text
ACTIVE      unusual movement relative to this market's own baseline
TRADEABLE   movement and liquidity are plausible relative to route costs
AVAILABLE   the market and selected route can accept an order now
```

None of these predicts direction. None should be presented as investment
advice or guaranteed edge.

## Decisions Supported by the Current Evidence

1. Market discovery is TICK's strongest product wedge. Asset search is a real
   attention problem, and existing tools use watchlists, rankings, and alerts
   to reduce it.
2. TICK should rank movement relative to each market's own regime and session,
   not compare raw percentage movement across unrelated asset classes.
3. The default screen should show one changing market explanation, one
   execution-cost relationship, and one wider context action. More data is not
   automatically more useful.
4. Once a position opens, market discovery yields to financial truth: estimated
   net PnL, cost recovery, exposure time, stop/liquidation distance, and close
   state.
5. Speed matters, but it must shorten work rather than shorten thought. The
   gesture can be one step because the risk preset and current terms are already
   visible.
6. Trade count, streaks, leaderboards, celebratory rewards, and loss-driven
   prompts are not product success metrics.
7. Cross-asset breadth strengthens the scanner because TICK can surface the
   market that is active now. It also adds market hours, gap, expiry, corporate
   action, and event-risk requirements that cannot be hidden in a generic price
   record.

## Dossier

- [`evidence.md`](evidence.md) - empirical findings about trader outcomes,
  attention, mobile interfaces, and crypto market behavior.
- [`workflow.md`](workflow.md) - the short-horizon trading workflow TICK should
  compress and the information budget for each stage.
- [`cross-asset-model.md`](cross-asset-model.md) - normalized market,
  availability, volatility, cost, and route primitives.
- [`tick-engine.md`](tick-engine.md) - the normalized discovery engine,
  directional and oscillating market shapes, temporal fit, consumer language,
  and shadow-validation requirements.
- [`tick-product-implications.md`](tick-product-implications.md) - product calls
  that follow from the evidence while preserving TICK's current philosophy.
- [`current-mvp-readiness.md`](current-mvp-readiness.md) - code-grounded audit
  of the present build, the proposed scanner formula, and the limits of the
  democratization claim.
- [`research-program.md`](research-program.md) - interviews, instrumentation,
  shadow scanning, experiments, and decision gates.
- [`sources.md`](sources.md) - annotated primary and official sources with
  evidence-strength notes.

The existing
[`../crypto_day_trader_workflows.md`](../crypto_day_trader_workflows.md)
remains the implementation-facing memo for the current chart and mobile loop.

## Evidence Standard

Claims are separated into three levels:

```text
EVIDENCE
Observed in account-level data, controlled experiments, protocol behavior, or
official market rules.

INFERENCE
A product interpretation that follows from evidence but has not been directly
tested in TICK.

HYPOTHESIS
A decision TICK must validate with its own users, telemetry, or shadow data.
```

Equity and futures research is useful for understanding attention, costs, and
short-horizon behavior, but it is not assumed to transfer perfectly to
high-leverage crypto perps. TICK needs its own evidence.
