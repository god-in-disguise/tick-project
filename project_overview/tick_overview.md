# TICK Product And Platform Overview

TICK is a market discovery and trading platform built around a simple idea:
show people what is moving, explain the market state visually, and make a
high-quality trade easy to execute.

The mobile product presents one market at a time instead of starting with a
pair list or terminal. Underneath it, TICK is building a shared discovery
engine, risk and cost model, execution router, position system, and accounting
layer. The same infrastructure can later power a professional web product and
partner API.

The current V1 uses gTrade/Gains on Arbitrum as its first live execution rail.
The product and backend are designed around normalized trading primitives so
that gTrade remains one adapter rather than becoming TICK's product model.
Additional venues will be introduced market by market after their pricing,
cost, execution, event, and recovery paths are measured.

This document describes both the long-term product and the current V1
implementation. V1-specific details are labelled so they are not mistaken for
the limits of the wider platform.

## Product Thesis

Most trading apps begin with a pair list or a professional terminal. TICK begins
with the question: **what is moving now?**

People should be able to understand a market's speed, direction, range,
participation, cost, and risk without reading six indicators. TICK converts
that information into live visual context, plain-language market states, and a
small number of trade terms.

The initial consumer loop is:

```text
discover movement
→ understand the current market shape
→ choose direction and risk
→ execute through the best available route
→ watch net exposure and risk
→ close and understand the result
```

Extreme leverage can make the loop visually immediate, but it is one
experimental configuration rather than the product definition. TICK should
select and explain leverage in relation to volatility, route cost, liquidation
distance, execution time, and the user's risk preset. Many useful trades will
belong at 25x, 50x, or 100x. Lower leverage and larger collateral can produce a
cleaner result than a small 500x position when fees and liquidation risk are
considered.

The app does not need to tell a user which direction to choose. It should make
the market's observed behavior legible enough that the user can make a better
decision.

## Reusable Product Blurb

TICK turns market discovery into a live feed. It scans supported markets,
explains what is happening in plain visual language, and lets a user move from
discovery to a live position without building an order ticket. The product
keeps price, risk, cost, execution state, and net result visible throughout the
trade.

V1 executes through gTrade/Gains on Arbitrum. TICK's engine and trading domain
are venue-agnostic, allowing future markets to use different execution rails
while the user keeps one product flow. Over time, the same engine will power a
broader mobile market feed, TICK Pro on the web, and partner integrations.

## Commercial Direction

TICK's first wedge is a retail mobile experience for short-duration crypto
trading. The wider opportunity is a cross-market discovery and execution layer:

- **TICK mobile:** a focused consumer experience for discovery, execution, and
  position watching;
- **TICK Engine:** market interpretation, tradeability, route quality, and
  availability;
- **TICK Router:** venue selection based on cost, latency, liquidity,
  capabilities, and health;
- **TICK Pro:** a data-rich web surface for experienced traders;
- **TICK API:** normalized discovery and execution primitives for partners.

This creates a path from an approachable retail product to infrastructure that
can support crypto, indices, commodities, FX, equities, and other markets when
data, venue access, and regulation allow.

Commercial models already under consideration in the project research are:

- trading fee share;
- routing rebates or spread economics;
- TICK Pro subscriptions for advanced data, alerts, and analytics;
- VIP fee tiers;
- partner or builder integrations;
- sponsored competitions and creator/referral programs.

The current V1 is focused on proving retention, execution quality, and market
discovery before selecting a final revenue mix.

## Product Surfaces

### Pulse

Pulse is the discovery screen.

- Ranks supported markets by observed activity and execution context.
- Shows price, recent movement, market character, and short live history.
- Uses plain-language states such as `SURGING`, `DUMPING`, `SWINGING`,
  `NEAR 90s HIGH`, and `NEAR 90s LOW`.
- Opens a selected market in TICK.

Pulse is intended to replace the static watchlist with a live map of where
short-term attention may be worthwhile. Ranking does not choose long or short.
It answers whether something meaningful is happening and whether the available
route can support a trade.

### TICK

TICK is the main trading surface.

- Displays a truthful live price tape from the shared backend feed.
- Shows the active amount, leverage, estimated costs, stop loss, take profit,
  exposure, and liquidation information where available.
- Swipe up opens long; swipe down opens short.
- Horizontal swipes change markets while the user is flat.
- An explicit Close button remains available during a position.
- Live PnL is an estimate of the net result if the position closed now.
- Opening, live, closing, closed, stopped, liquidated, failed, and recovery
  states are visually distinct.
- The 90-second live tape can expand into a one-hour context view using the
  same price source.

### Me

Me is the account surface.

- Shows available USDC or the active demo balance.
- Provides deposit and withdrawal controls in Live mode.
- Holds the active amount, leverage, stop-loss, and take-profit preset.
- Shows completed trades, net results, win rate, and liquidation filtering.
- Switches between the Live and Demo trading profiles.
- Resets a demo season after confirmation.
- Provides account and sign-out controls.

## TICK Engine

TICK Engine is the shared interpretation layer behind Pulse, the trade screen,
notifications, Pro, and the future API.

It turns raw market and route data into six primitives:

| Primitive | Product question |
| --- | --- |
| `ACTIVE` | Is movement unusual for this market relative to its own recent behavior? |
| `SHAPE` | Is price surging, dumping, swinging, breaking out, reversing, or quiet? |
| `PARTICIPATION` | Is the move supported by elevated activity, volume, open interest, or other available participation data? |
| `CONTEXT` | Where is price inside its short and wider ranges? |
| `TRADEABLE` | Is the movement large and clean enough relative to cost, spread, liquidity, and execution latency? |
| `AVAILABLE` | Can this user, preset, wallet, market, and venue route execute now? |

The first regime model separates two common short-horizon situations:

- **Directional:** momentum, continuation, breakout, and impulse behavior.
- **Oscillating:** range-bound movement, repeated reversals, and short-term
  mean reversion.

These regimes should change how the interface explains the market. A
directional tape may emphasize impulse, range break, and acceleration. An
oscillating tape may emphasize swing size, recent extremes, and reversal
frequency. Neither state is an instruction to buy or sell.

The engine should combine:

- normalized price and timestamp data;
- realized volatility over several windows;
- range position and breakout behavior;
- update cadence and price-change activity;
- real volume and open interest where licensed and available;
- spread, price impact, fees, funding, and expected slippage;
- measured open and close latency;
- venue and market health;
- user balance, limits, preset, and regional availability.

Discovery data can come from broader and richer sources than the execution
venue. Final quote, liquidation, stop, fill, and PnL truth must use the chosen
route's own rules and price inputs.

Every engine version should be shadow-scored against what happened after the
signal at 10 seconds, 30 seconds, 60 seconds, and five minutes. Evaluation
should measure continuation, reversal, favorable and adverse excursion, regime
lifetime, route cost, and whether the opportunity survived execution latency.
This turns Pulse from an attractive volatility list into an evidence-based
trading tool.

## Current V1

The current implementation proves the complete mobile loop with one live rail:

- gTrade/Gains execution on Arbitrum;
- invite-code accounts and platform-created wallets;
- USDC deposits and withdrawals;
- platform-paid ETH gas with USDC accounting;
- real market quotes, venue-native stop loss and take profit;
- durable open and close jobs;
- execution-event tracking and final wallet reconciliation;
- a shared market feed, 90-second tape, and one-hour context;
- isolated Live and Demo profiles.

gTrade is the V1 rail because it provides live markets, high leverage,
delegated execution, user-owned positions, and observable onchain settlement.
Its fee model and two-transaction oracle flow are specific to this adapter.
They should not determine how another venue is represented inside TICK.

## User Actions

### Join

Private-alpha users enter with an invite code. The backend issues a signed
session JWT and restores the same user and wallet on later logins with that
code. Email linking and Google authentication are not active.

### Deposit

Each user has one platform-created Arbitrum wallet. The app displays its USDC
deposit address and refreshes the onchain balance. Only Arbitrum USDC is treated
as trading collateral.

### Configure

The active preset is applied to each opening gesture:

- collateral amount;
- leverage;
- optional venue stop-loss budget;
- optional venue take-profit budget.

The venue can require a higher minimum collateral for a specific market. The
UI must show that requirement before opening.

### Open

1. The PWA requests a short-lived quote.
2. The quote captures the selected market, side, collateral, leverage, costs,
   stop, take profit, liquidation estimate, profile, season, and venue terms.
3. The API validates the session, quote age, balance, active-position rule, and
   idempotency key.
4. Postgres stores the trade intent, execution attempt, and opening position
   before a job is queued.
5. The worker builds and signs the venue transaction.
6. A delegated platform agent submits the transaction and pays Arbitrum gas.
7. gTrade records the market-order initiation onchain.
8. Its oracle fulfiller submits a second callback transaction that creates the
   position at the venue.
9. Direct contract events, the Gains event stream, and position snapshots feed
   the local state reducer.
10. The PWA receives the confirmed position state.

A successful initiation transaction does not by itself mean the position is
filled. The venue callback establishes economic execution. Recent canaries
commonly reached visible execution in roughly two to four seconds, with
variation from RPC, Arbitrum sequencing, and the venue oracle. This is not an
SLA.

### Watch

The shared market stream updates the chart and estimated PnL. Entry,
break-even, stop, take-profit, and liquidation overlays use the position's real
terms. The UI stops treating a position as exposed when an authoritative close,
stop, or liquidation event is observed.

### Close

1. The API locks the current position and creates an idempotent close intent.
2. A worker immediately submits the close from cached normalized position
   state.
3. The venue validates whether the position still exists.
4. The gTrade callback executes the close.
5. The UI moves to `Closed · finalizing result`.
6. Venue cash flow, wallet balance, trading fees, and platform gas charges are
   reconciled.
7. The final net result replaces the estimate.

The close path does not block on a pre-submit REST revalidation during normal
operation. Recovery checks run after submission or when local state is unknown.

### Withdraw

The user enters an Arbitrum destination and USDC amount. The backend validates
balance and account state, stores an idempotent withdrawal request, signs from
the user's platform wallet, broadcasts it, and records gas accounting.
Withdrawals are unavailable while a position or withdrawal is already active.

## Live And Demo Profiles

Every account has two isolated profiles.

**Live**

- Uses the user's real USDC wallet.
- Sends real delegated gTrade transactions.
- Includes real venue fees, market movement, and platform gas charges.
- Preserves live positions, history, reconciliations, and balance.

**Demo**

- Starts each season with `$1,000`.
- Uses the same real market feed and venue quote calculations.
- Simulates open fills after approximately `1.25-1.65s`.
- Simulates manual close fills after approximately `0.95-1.35s`.
- Requotes at simulated fulfillment time instead of filling at the swipe price.
- Applies opening cost, closing cost, PnL, stop loss, take profit, and
  liquidation.
- Runs a backend risk monitor even when the phone is backgrounded.
- Never signs or broadcasts a blockchain transaction.

A user cannot switch profiles or reset Demo while any position is active.

Resetting Demo creates a new season and restores `$1,000`. The previous
season's starting balance, ending balance, realized PnL, trade count, win count,
and reset time are stored in an append-only reset record.

## Technical Architecture

```text
iOS PWA on Vercel
        |
        | HTTPS + JWT + server events
        v
FastAPI API on DigitalOcean
        |
        +-- Postgres: durable users, wallets, profiles, trades and ledger
        +-- Redis: job queue, cache and live distribution
        +-- ARQ worker: open, close, withdrawal and reconciliation jobs
        +-- Market feed: shared live prices and retained bars
        +-- Venue events: direct gTrade/Gains execution observations
        +-- Caddy: TLS and API reverse proxy
        |
        v
Venue adapters
        |
        +-- gTrade/Gains on Arbitrum: active live route
        +-- Aark: researched and canary-tested, not an active product route
```

The backend is one modular Python codebase with separate process roles. It is
not split into microservices.

### Data Model

The durable core includes:

- `User` and authentication identities;
- encrypted per-user `WalletAccount`;
- Live and Demo `TradingProfile`;
- immutable `Quote`;
- user-authorized `TradeIntent`;
- transaction-level `ExecutionAttempt`;
- normalized economic `Position`;
- accounting `Reconciliation`;
- append-only `LedgerEvent`;
- `Withdrawal`;
- audited `DemoProfileReset`;
- retained market observations and one-second bars.

Trade intent, transaction execution, economic exposure, and financial
reconciliation are separate lifecycles. Workers and venue listeners store
observations; normalized position state is persisted before it is published.

### Wallet And Gas Model

The current private alpha is custodial:

- TICK creates one Arbitrum wallet per user.
- Private keys are encrypted before storage in Postgres.
- The encryption key lives in the backend environment.
- The user wallet owns its USDC and gTrade position.
- A platform agent is delegated to open and close for the user.
- The platform agent pays ETH gas.
- Gas is priced in USD and recorded as a USDC charge in the trade ledger.

This avoids requiring users to hold ETH. Encrypted database custody is suitable
for a controlled alpha, not the intended final security model. KMS/HSM-backed
keys, external wallets, embedded-wallet providers, stronger operator controls,
and legal custody review remain future work.

### Market Data

One backend feed is shared by every user. The system does not open one venue
price connection per phone.

- The live chart stores real observations only.
- Rendering can animate between real observations without modifying history.
- One-second bars are retained for context and research.
- Current retention is 24 hours for the selected market universe.
- The live view uses roughly 60-90 seconds.
- The context view can show one hour.
- Execution quotes and fills use the active venue's price and rules.

Longer-term discovery may use broader market-data sources, while final quote,
risk, and execution truth must remain tied to the selected venue.

### API

The PWA currently uses a private REST API plus a server event stream.

Main endpoint groups:

- invite authentication and session restoration;
- account and trading-profile state;
- market list, tape, chart, and retained bars;
- wallet balances, deposit address, withdrawals;
- quote, open, close;
- Demo mode switch and season reset;
- account state and event delivery.

Write operations require JWT authentication and idempotency keys. The same key
with a different payload is rejected. Jobs are stored before execution. The
signed transaction hash is persisted before ambiguous live broadcasts where
the venue path supports it.

This API is not public or versioned for external developers. A future partner
API should expose the same venue-agnostic primitives rather than gTrade
contract details.

## Venue Abstraction

The consumer app and core domain work with:

- market availability;
- collateral and notional;
- leverage limits;
- opening and closing cost;
- stop, take profit, and liquidation;
- expected open and close time;
- position and settlement state.

Venue-specific contract calls, indices, decimals, events, and recovery rules
remain inside adapters.

The V1 route is gTrade. Future adapters can represent faster order books,
lower-fee perps, higher-leverage engines, or cross-asset venues without
changing the user's basic flow. Each route must expose the same normalized
capabilities:

```text
markets
leverage and collateral limits
all-in opening and closing cost
quote freshness and slippage
open and close lifecycle
position, stop, take profit, and liquidation state
realized result and reconciliation
health, latency, and recovery status
reward or points eligibility when known
```

The router should consider eligibility, availability, venue health, all-in
cost, liquidity, leverage fit, measured latency, and reconciliation quality.
Reward programs are secondary to execution quality.

Users of the main mobile product should not need to choose a venue for every
trade. TICK can select the route that fits the market and preset. TICK Pro can
later expose venue and route comparison for users who want direct control.

gTrade is the only active live venue today. Aark has been researched and
canary-tested, but seamless opening requires a working partner authorization
path. Other venue research remains in the repository and is not presented as a
production integration.

## Points Program

TICK plans to have its own points program. The earning rules, accounting model,
and benefits have not been defined yet.

Because TICK is venue-agnostic, it can also track whether an eligible route has
an active venue points or rewards program. Users may then receive the available
venue benefit when that route is already suitable for the trade. TICK should
not promise token value or select worse execution only to chase rewards.

## Current V1 Boundaries

These are boundaries of the present build rather than the intended product:

- access is invite-only;
- gTrade is the only active live route;
- accounts use platform-created wallets with environment-managed encryption;
- one position and one command can be active per user;
- execution uses market orders and full closes;
- partial close and position resize are not exposed;
- scanner labels describe observed conditions and are still being calibrated;
- available cost and leverage follow gTrade's market rules;
- execution time includes Arbitrum and gTrade oracle latency;
- operator tooling, policy controls, security hardening, and jurisdiction rules
  remain roadmap work.

The narrow V1 lets the team measure one complete route before expanding the
market universe and routing system.

## Roadmap

### 1. Complete The Mobile V1

- Run repeated Live and Demo cycles with teammates.
- Track execution latency, failures, liquidations, PnL differences, and resets.
- Improve the gesture, chart context transition, and mobile state presentation.
- Refine presets so amount, leverage, cost, and risk fit each market.
- Make the market's current shape and context easier to read without turning
  the phone into a professional terminal.
- Add operator views for every intent, transaction, event, and reconciliation.

### 2. Calibrate TICK Engine

- Centralize cross-market activity scoring.
- Distinguish directional and oscillating market regimes.
- Add participation, range context, tradeability, and route availability.
- Shadow-score signals against 10-second, 30-second, 60-second, and five-minute
  outcomes.
- Use the measured outcomes to improve ranking, labels, notifications, and
  suggested market configuration.

### 3. Add Venue Routing

- Certify a second live adapter using measured cost, fill speed, event accuracy,
  and recovery.
- Route each market through the best eligible venue instead of treating one
  protocol as the product.
- Track route-specific fees, leverage, liquidity, availability, and rewards.
- Keep the mobile experience stable while adapters change underneath it.

### 4. Expand Markets And Data

- Add richer discovery inputs such as real volume, open interest, funding,
  spread, depth, and liquidation activity where reliable sources are available.
- Separate broad discovery data from route-specific execution truth.
- Expand from crypto toward indices, commodities, FX, and equities where
  market data, venue support, and regulation allow.
- Build alerts around observed market events rather than directional advice.

### 5. Launch TICK Pro Web

TICK Pro will expose more of the same engine rather than becoming a separate
trading backend.

Planned Pro controls include:

- multi-chart workspaces and longer timeframes;
- order types, bracket orders, reduce-only and partial close;
- funding, open interest, volume, spread, depth, and liquidation context;
- venue and route comparison;
- advanced leverage and margin controls;
- detailed execution timelines and fee attribution;
- alerts, watchlists, saved layouts, and API access.

The consumer PWA remains the focused mobile product. Pro web serves traders who
want more control and makes the shared execution infrastructure inspectable.

### 6. Platform And Distribution

- Upgrade custody and operational key controls.
- Add regional eligibility, risk policy, disclosures, and incident controls.
- Expose a versioned partner API after the internal primitives stabilize.
- Let partners consume normalized market discovery, quotes, execution state,
  positions, and reconciliation without integrating each venue themselves.
- Support TICK's own points program and eligible venue programs once their
  rules and user benefits are defined.

## Long-Term Product Standard

TICK should make trading easier to understand while improving the quality of
the decision and execution.

The platform should be able to:

1. scan a broad market universe and find meaningful activity;
2. describe whether a market is directional, oscillating, breaking, reversing,
   active, or quiet;
3. distinguish an interesting chart from a tradeable opportunity;
4. choose an eligible venue using cost, liquidity, latency, reliability, and
   market coverage;
5. match amount and leverage to volatility, route economics, and user risk
   instead of treating maximum leverage as the default;
6. show the important context and terms without requiring terminal expertise;
7. execute through a durable, recoverable state machine;
8. show estimated and final net outcomes after venue cost and gas;
9. learn from later market behavior and real fills so discovery improves over
   time.

The intended product family is:

```text
TICK mobile
Simple discovery, execution, position watching, and account management.

TICK Engine
Shared market interpretation, tradeability, availability, and route scoring.

TICK Router
Venue-agnostic quote, execution, position, and reconciliation infrastructure.

TICK Pro web
The same engine with professional data and controls exposed.

TICK API
Normalized discovery and execution capabilities for partner products.
```

The core message is:

> Find the market moving now. Understand the move. Trade it through the route
> that fits.

## Repository Sources

This overview consolidates decisions and verified implementation details from:

- [`tick_real_build_spec.md`](tick_real_build_spec.md);
- [`tick_product_infra.md`](tick_product_infra.md);
- [`market_research.md`](market_research.md);
- [`flow_tech_doc.md`](flow_tech_doc.md);
- [`tick-engine.md`](../research/market/day-trading/tick-engine.md);
- [`builds/tick-mvp/README.md`](../builds/tick-mvp/README.md);
- [`research/venues/README.md`](../research/venues/README.md).
