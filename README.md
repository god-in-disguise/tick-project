# TICK Research Project

This repository now separates the proven local prototype from the next production-shaped MVP.

## Layout

- `project_overview/` - product, infra, and build-spec documents.
- `research/` - venue research, market notes, and live canary experiments.
- `builds/local-mvp/` - frozen prototype apps and local live-trading MVP code.
- `builds/tick-mvp/` - clean production MVP scaffold for backend on DigitalOcean and PWA frontend on Vercel.

## Current Decision

The local MVP is frozen as the reference implementation. It proved the core loop:

- live gTrade/Gains execution on Arbitrum;
- mobile-first trading UI;
- native stop-loss handling;
- wallet-delta reconciliation;
- chart and execution latency lessons.

New production work should happen in `builds/tick-mvp/`. Pull proven pieces out of `builds/local-mvp/`; do not keep productionizing the prototype in place.

Current production-shaped status:

- `builds/tick-mvp/backend` runs with Docker Compose, Postgres, Redis, an ARQ worker, and venue-events process. The MVP shares one live market feed inside the API process.
- Auth/session, platform wallet creation, deposit address, quote, open intent, close intent, idempotency, and withdrawal contracts are wired.
- Live gTrade execution has not yet been extracted into the new backend; the local MVP remains the live execution reference.
- The first frontend target is PWA for fast sharing, but the UX should follow the local Expo canary.

## Current Work Order

1. Finish the current product-surface pass:
   - landing-page composition;
   - first-use gesture guide;
   - swipe behavior and transitions;
   - chart presentation and responsive iOS PWA polish.
2. Begin TICK Engine implementation after that interaction baseline is stable.

## TICK Engine

The engine design is documented; implementation and empirical calibration are
still pending. The working specification is
[`research/market/day-trading/tick-engine.md`](research/market/day-trading/tick-engine.md).

TICK Engine is the shared server-side discovery and interpretation layer. It
will normalize market data, execution economics, and user-route constraints
into six product primitives:

- `ACTIVE` - is meaningful movement happening relative to this market's normal
  behavior?
- `SHAPE` - is the market surging, dumping, swinging, breaking, reversing, or
  quiet?
- `PARTICIPATION` - is genuine market involvement elevated?
- `CONTEXT` - where is price within its short-term and wider ranges?
- `TRADEABLE` - can the observed movement plausibly survive route cost and
  measured execution latency?
- `AVAILABLE` - can this user, wallet, preset, market, and route execute now?

The first shape model separates two short-horizon regimes:

- `DIRECTIONAL` - momentum, continuation, and breakout behavior.
- `OSCILLATING` - range-bound, reversing, and short-horizon mean-reverting
  behavior.

Consumer stories such as `SURGING`, `DUMPING`, `SWINGING`, `RANGE BREAK`,
`REVERSING`, and `QUIET` describe observed conditions. They must not choose a
side or imply guaranteed continuation.

Before TICK Engine becomes a product claim, its versioned signals must be
shadow-scored from both signal time and executable fill time over 10-second,
30-second, 60-second, and 5-minute horizons. Evaluation must include regime
lifetime, continuation and reversal, favorable and adverse excursion, route
cost, and whether the opportunity survived measured execution latency.
