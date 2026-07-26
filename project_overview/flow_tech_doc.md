# TICK Tech Doc: Perp-Agnostic Trading Router

This is the first technical direction for TICK.

Status: older router memo. Use `tick_real_build_spec.md` for current build decisions. In particular, the current MVP is one live gTrade/Gains route plus shadow/research venues, and the current demo/private-MVP wallet decision is platform-created Arbitrum wallets with encrypted Postgres key material.

## Core Thesis

TICK should not start as its own exchange.

TICK should start as a mobile trading wrapper and routing layer across perp venues. The user gets one simple trading flow. The backend chooses or recommends the best venue based on execution quality, all-in cost, market availability, reliability, leverage limits, and reward upside.

The user-facing promise:

> Open the app, see the market moving now, trade with a preset, and move on.

The backend promise:

> Route that intent to the best available venue without exposing venue complexity in the main TICK product.

The launch can be crypto-first, but the architecture should not be crypto-only. Ostium-style cross-asset venues make it possible for the same feed to show crypto, stocks, indices, commodities, and FX when the user is eligible and the venue supports the market.

## What The Backend Does

The backend is not only an API server. It is the product engine.

It needs to:

- Ingest market data from multiple perp venues
- Rank markets for the feed
- Normalize markets, asset classes, positions, fees, leverage, and risk
- Route trade intents to the best venue
- Select sensible leverage based on volatility and route cost
- Track rewards and points programs where available
- Reconcile positions across venues
- Keep a full execution and risk audit trail
- Support the main TICK product and TICK Pro from the same core system

## High-Level Architecture

```text
Mobile App
  |
  | Trade intent / feed request / account state
  v
TICK API
  |
  +-- Feed Engine
  +-- Risk Preset Service
  +-- Cost And Leverage Engine
  +-- Route Scorer
  +-- Execution Router
  +-- Rewards Tracker
  +-- Position Reconciler
  +-- Audit Log
  |
  v
Venue Adapter Layer
  |
  +-- Aster
  +-- Lighter
  +-- Ostium / cross-asset venue
  +-- Other perp venues later
```

The app should never directly depend on a venue's API shape. It talks to TICK's normalized backend.

## First Stack

Keep the first backend boring and reliable.

Recommended stack:

- Backend: TypeScript with Node.js, or Go if we want stricter performance from day one
- API: REST for account/order actions, WebSocket for feed and position updates
- Database: Postgres
- Cache/live state: Redis
- Analytics later: ClickHouse
- Job/event processing: start with Postgres queues or Redis streams, move to NATS/Redpanda when needed
- Mobile app: React Native with TypeScript
- Charts/visuals: lightweight charting first, advanced TradingView-style components for TICK Pro later

Recommended starting shape:

- Modular monolith first
- Separate modules for feed, routing, execution, rewards, and reconciliation
- No microservices until volume or team size forces it

The hard part is correctness, not web scale. Routing, signing, and position state must be clean before the system becomes distributed.

## Product Modes

### Main TICK Product

The main TICK product hides venue complexity.

The user configures a preset before entering the feed:

- Margin size
- Leverage range
- Max loss
- native stop/loss budget and manual close preference
- Margin mode
- Slippage limit

Then every market card uses that active preset.

When the user swipes long or short, the backend turns that into a normalized trade intent, checks risk, chooses a route, and executes.

The main TICK product should show:

- Market
- Direction
- Active preset
- Estimated liquidation
- Estimated fee
- Estimated spread/slippage
- Suggested leverage for this market
- Estimated max loss
- Rewards active / not active
- Route label such as "Best route selected"

It should not force the user to compare venues on every trade.

### TICK Pro

TICK Pro exposes the venue and execution details.

TICK Pro users should see:

- Venue
- Funding
- Open interest
- Spread
- Depth
- Fees
- Slippage estimate
- Reward/points status
- Routing reason
- Manual venue override
- Position controls

Same backend, more detail.

## Normalized Trading Model

The core abstraction is a trade intent.

```text
TradeIntent
  userId
  presetId
  marketSymbol
  assetClass
  side: long | short
  marginUsd
  leverage
  takeProfitPct
  stopLossPct
  slippageBps
  estimatedRoundTripCostUsd
  mode: tick | tick_pro
```

The venue adapter translates this into the venue-specific API calls.

The key is that TICK owns the user intent model. Venues are execution targets.

## Cost And Leverage Model

Short holds are not expensive because of time. They are expensive when opening and closing fees, spread, and slippage are high relative to margin.

The core formula:

```text
round-trip fee as % of margin = 2 * taker fee * leverage
```

This is why 100x can be either excellent or bad depending on the route. On a low-fee route in a hot market, 100x creates the live-PnL loop TICK wants. On a normal-fee route in a slow market, fees can eat the move before the user has a chance to react.

The Cost And Leverage Engine should output:

```text
LeverageDecision
  requestedLeverage
  allowedLeverage
  suggestedLeverage
  maxVenueLeverage
  estimatedOpenFeeUsd
  estimatedCloseFeeUsd
  estimatedSpreadCostUsd
  estimatedSlippageUsd
  fundingRisk: none | possible | likely
  reason
```

The main TICK product can keep this simple: "100x available", "50x suggested", or "fees high on this route." TICK Pro should show the math.

## Venue Capabilities

Different venues are similar at the basic level, but not identical.

Each adapter should expose capabilities:

```text
VenueCapabilities
  assetClasses: crypto | stock | index | commodity | fx
  supportsMarketOrders
  supportsLimitOrders
  supportsAtomicTPSL
  supportsReduceOnly
  supportsIsolatedMargin
  supportsCrossMargin
  supportsBuilderFees
  supportsRewardAttribution
  supportsSessionKeys
  supportsPartialFills
  maxLeverageByMarket
  feeSchedule
  fundingSchedule
  executionModel: orderbook | oracle | pool
```

The frontend and router should use this instead of assuming all venues behave the same.

Example:

- Lighter is closer to a CEX-style order book venue.
- Aster is strategically relevant for crypto perps and points/reward upside.
- Ostium-style venues are important for cross-asset perps: stocks, indices, commodities, and FX.
- GMX is more pool/oracle based.

TICK should normalize the simple trade path, but TICK Pro can expose venue-specific behavior.

## Route Scoring

Routing should not blindly chase rewards.

Execution quality must come first. Points and reward upside are valuable, but only after a venue passes basic quality checks.

Route score should consider:

```text
RouteScore =
  executionQuality
  + liquidityScore
  + spreadScore
  + feeScore
  + leverageFitScore
  + reliabilityScore
  + marketAvailabilityScore
  + assetCoverageScore
  + rewardUpsideScore
  - riskPenalty
```

Hard filters before scoring:

- User is eligible for the venue
- Market exists on the venue
- Venue is live
- Required margin mode is supported
- Max leverage is supported
- Estimated round-trip cost is acceptable for the selected leverage
- Slippage estimate is inside user preset
- Venue risk status is acceptable

Only after those pass should the router consider points or rewards.

## Rewards And Points Upside

This is a real strategic angle.

If users are going to trade perps anyway, TICK can help them route flow through venues where there is additional upside:

- Venue points
- Campaigns
- Trading rewards
- Partner attribution
- Airdrop/TGE exposure
- Builder or integrator economics

But this must be framed carefully.

TICK should not promise airdrops or route users into bad execution just to farm points. The correct framing is:

> Trade through one interface and capture eligible venue rewards when the route is good.

The backend should track reward metadata:

```text
RewardProgram
  venue
  status: active | paused | ended | unknown
  rewardType: points | feeRebate | campaign | partner
  eligibleMarkets
  eligibilityRules
  sybilRestrictions
  washTradingRestrictions
  lastUpdatedAt
```

The router can then show:

- "Rewards active"
- "Points eligible"
- "No reward program"
- "Reward status unknown"

For the main TICK product, keep this simple. For TICK Pro, show more detail.

## Execution Flow

Main TICK swipe execution should feel instant, but the backend still needs strict preflight checks.

```text
1. User opens market feed.
2. Feed Engine shows ranked market cards.
3. User swipes long or short.
4. App sends TradeIntent to TICK API.
5. Risk Preset Service validates the user's preset.
6. Route Scorer selects best venue.
7. Execution Router creates venue-specific order plan.
8. Venue Adapter submits order.
9. Venue-native stop is attached atomically or confirmed immediately after, depending on venue support.
10. Position Reconciler confirms final state.
11. App shows result card.
12. Audit Log stores every event.
```

If a venue does not support atomic stop protection, TICK must make that clear internally and treat the trade as higher risk until protection orders are confirmed. A backend-calculated stop is not equivalent to a venue-native stop.

## Position Reconciliation

This is a critical backend piece.

Users will have positions across venues. The app must show one clean view while preserving venue truth.

Position state should be reconciled from:

- TICK's submitted orders
- Venue open orders
- Venue fills
- Venue positions
- Venue account balances
- Venue liquidation and funding data

TICK should never assume an order succeeded only because the request was sent.

Core states:

```text
TradeExecution
  created
  preflight_passed
  routed
  submitted
  partially_filled
  filled
  tpsl_pending
  protected
  rejected
  canceled
  failed
  reconciled
```

The app should only show "trade live" after the venue confirms the position.

## Volatility Explorer

The volatility explorer is the product moat.

The feed is only the interface. The engine underneath must find day-trading moments and decide whether they are actually tradeable after fees, spread, slippage, liquidity, funding risk, leverage limits, and venue reliability.

Inputs:

- Price movement
- Realized volatility
- Asset class
- Volume acceleration
- Open interest changes
- Funding changes
- Spread
- Depth
- Liquidation activity if available
- Recent execution quality
- Estimated round-trip cost
- Suggested leverage range
- Reward program availability
- Venue reliability

Main TICK output:

- Cold
- Warming up
- Fire
- Rewards active
- Tradeable / not tradeable

TICK Pro output:

- Full metrics
- Route comparison
- Venue-specific data

The volatility explorer should rank markets by tradeability, not just raw volatility.

## Data Storage

Recommended first stack:

- Postgres for users, presets, orders, positions, reward programs, audit logs
- Redis for live feed cache, route cache, and hot market state
- ClickHouse later for ticks, candles, execution analytics, and backtesting
- Object storage for exported audit logs and reports

Start simple, but keep the data model clean. We will need historical execution data to improve routing.

## Signing And Wallet Model

Current MVP model:

- User signs in with Google
- TICK creates a per-user Arbitrum wallet
- wallet private key is encrypted in Postgres using an env encryption key
- platform workers execute approved setup/trading/withdrawal actions
- platform pays gas where possible and records USDC gas charges

This is a private-MVP/demo decision. For broader external users, bounded permissions, revocation, withdrawal controls, and stronger signing isolation become mandatory.

Session limits should include:

- Expiry
- Max notional
- Max leverage
- Max number of actions
- Allowed markets
- Allowed venues

This is important for one-gesture trading. The user should not sign every swipe, but the app also should not have unlimited trading power.

## Venue Adapter MVP

Start with one live venue and one or more shadow/research venues.

One live venue keeps the first real execution lifecycle explainable. Shadow venues force the abstraction to stay real without doubling live money risk before state, PnL, and reconciliation are deterministic.

Current order:

1. gTrade/Gains live route
2. Lighter/Aster/Pacifica research or shadow checks
3. Ostium for cross-asset expansion
4. Hyperliquid or GMX later

Reasoning:

- gTrade/Gains is the selected first route because the local canary proved real wallet-native high-leverage execution.
- Aster is strategically relevant for crypto perps, reward upside, and direct competitive learning.
- Lighter gives a strong low-cost/points angle and forces the adapter abstraction to be real.
- Ostium is the cross-asset unlock: stocks, indices, commodities, and FX in the same feed.
- Hyperliquid gives serious trader credibility later, but it does not need to be first if the MVP thesis is the main TICK product plus routing.
- GMX is useful for one-click/onchain style, but less clean for the first TICK Pro path.

## MVP Backend Scope

MVP should include:

- User account
- Wallet/session setup
- Risk presets
- Market feed
- Main TICK route scoring
- Aster adapter
- Lighter adapter
- Cost And Leverage Engine
- Open/close position
- venue-native stop support
- Unified position view
- Reward program metadata
- Execution audit log

MVP should not include:

- Own matching engine
- Custody
- Portfolio margin
- Copy trading
- Full social graph
- Complex multi-leg strategies
- Binary options

## Main Risks

### Routing Risk

Bad routing destroys trust. If reward chasing worsens fills, users will leave.

### Abstraction Risk

Venue behavior is not identical. The abstraction must expose capabilities and not hide important differences.

### Signing Risk

One-gesture trading needs session keys, but session keys create security risk. Permissions must be bounded.

### Position State Risk

If the app shows wrong position state, users can lose money. Reconciliation must be treated as core infrastructure.

### Compliance Risk

Perp DEX routing is still derivatives access. The backend needs region gating and venue eligibility checks from the beginning.

## Product Principle

The main TICK product hides venue complexity.

TICK Pro exposes venue choice.

The router optimizes for:

1. Safe execution
2. Good liquidity
3. Low all-in cost
4. Reliable venue state
5. Reward upside

Points are upside. Execution quality is the product.

## First Build Milestones

### Milestone 1: Paper Router

- Ingest market data from the live venue and at least one shadow/research venue
- Normalize markets
- Rank feed cards
- Simulate routing decisions
- Show why route was selected

### Milestone 2: Live Adapter One

- Add first live execution venue
- Support one market and one preset
- Open/close position
- Track fills and positions
- Store audit trail

### Milestone 3: Live Adapter Two

- Add second venue
- Implement real route comparison
- Add reward status into route score
- Add manual override in TICK Pro

### Milestone 4: Main TICK Product

- Preset-based one-gesture trading
- Visible risk terms
- Result cards
- Hot/cold market feed

### Milestone 5: TICK Pro

- Venue comparison
- Funding/OI/spread/depth
- Advanced position controls
- More transparent route reasoning

## Working Definition

TICK is not a CEX at the start.

TICK is a perp-agnostic mobile trading router.

The frontend is the arcade.

The backend is the router.

The moat is the volatility explorer plus routing data.

## Reference Venues

- Hyperliquid: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api
- Lighter: https://docs.lighter.xyz/
- Lighter Partner Attribution: https://docs.lighter.xyz/integrations/partner-attribution
- Aster: https://docs.asterdex.com/
- Ostium: https://docs.ostium.io/
- GMX V2: https://docs.gmx.io/docs/trading/v2/
