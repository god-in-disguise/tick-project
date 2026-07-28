# TICK Real Build Spec

This is the practical build spec for the real TICK backend and frontend.

It combines the earlier product direction with what we learned from the mobile mockup, the live Ostium tests, and the live gTrade/Gains canary.

## One-Line Product

TICK is a mobile-first trading app that finds live market volatility, shows whether current movement clears estimated costs, lets an eligible user take a simple long or short position, shows real net PnL, and lets them close fast.

The core loop:

```text
market moves -> TICK ranks the opportunity -> user opens app -> takes a side -> watches live net PnL -> closes -> comes back when volatility appears again
```

The moat is not the long/short button. The moat is the volatility explorer that decides what is actually tradeable after fees, spread, slippage, leverage limits, and route quality.

The durable advantage is the dataset behind it. TICK should store every candidate market moment, route estimate, execution result, actual cost, failure, reconciliation outcome, and subsequent price path. That data should continuously improve scanner thresholds and route estimates.

Product principle:

```text
truth is a hard constraint
engagement is the optimization target
friction appears only when TICK cannot maintain valid terms or reliable execution
```

## Source Of Truth

This document is the current real-build source of truth for backend and frontend.

Supporting docs:

- `flow_concept.md` for product concept.
- `tick_product_infra.md` for broader product/infra direction.
- `flow_tech_doc.md` for earlier router thinking.
- `research/venues/` for dated venue facts, measurements, and test decisions.
- `builds/local-mvp/tick-mvp-local/` and `builds/local-mvp/tick-mvp-local-expo/` for the local live prototype.

If this document conflicts with older docs, use this document.

## Current Execution Decisions

These decisions override the older two-venue-start and Ostium-first language in earlier docs.

| Question | Decision |
| --- | --- |
| First live MVP venue | gTrade/Gains on Arbitrum. One live venue only until the full lifecycle is explainable. |
| Venue abstraction | Mandatory. Product primitives are fees, open/close latency, market availability, leverage availability, health, cost, and reconciliation quality. Do not leak gTrade-specific concepts into product surfaces. |
| Other venues | Keep Aark, Aster, Lighter, Pacifica, GMTrade, and Ostium as research, probes, or shadow quote/health collectors. Aark passed a live delegated round trip but remains disabled until partner authentication or TICK-domain reCAPTCHA authorization exists. Do not route consumer live flow to these venues yet. |
| 500x | Internal engineering/demo mode only. It catches attention, but it is not the private-beta default. |
| External leverage default | 25x normal, 50x when economics and activity allow, 100x advanced/gated. |
| PnL display | Show estimated net result if closed now, not gross mark movement. |
| Execution truth | Direct callback/on-chain execution logs are the normal authoritative path. WebSocket is the fast path. REST/history/balance are explicit recovery and reconciliation paths. |
| Wallet delta | Keep as the canary aggregate invariant. Store venue-derived cash flows and PnL fields too. |
| User positions | One active position and one in-flight command per user in V1. |
| Scanner gating | Main TICK feed blocks opening unless cost coverage, freshness, venue health, and risk checks pass. |
| Wallet model | Current MVP uses Google login and platform-created Arbitrum wallets with encrypted Postgres key material. This is deliberate for the demo/private MVP, not a final broad-public custody architecture. |
| Wallet execution | V1 uses one platform-created Arbitrum wallet per user plus a TICK execution agent. The user wallet owns collateral and positions; after one-time delegation and allowance setup, the agent submits normal gTrade opens/closes and pays ETH gas. TICK charges actual gas to the user's spendable-USDC ledger. |
| Allowance | Max allowance is local/internal only. External users should get bounded allowance or explicit revocation, unless the cohort is intentionally founder/demo wallets. |
| Build strategy | Strangler-style extraction. Preserve the working gTrade behavior and mobile loop, but move execution truth to Postgres, durable workers, event journals, and a single reducer. |

## What We Learned From The Live MVP

### 1. Gross PnL Is Dangerous

The app must never show gross chart PnL as if it is profit.

In the live Ostium and gTrade/Gains tests, trades could look green by mark-to-entry movement while the wallet balance still dropped because fees/reserves were larger than the move.

Example from the test wallet:

```text
$20 ticket, 100x ETH long
gross chart PnL: about +$1.65
real wallet delta: about -$0.46
```

Reason: the actual active collateral was about `$17.90`, not `$20`. Roughly `$2.10` was consumed by the venue's execution cost/reserve model.

gTrade/Gains showed the same lesson at higher leverage:

```text
$10 ticket, 500x degen pair
round-trip fee drag: roughly $1.85-$2.00 before meaningful market movement
```

For this product, the main PnL number must answer: "approximately what would this position return if closed now?"

Product rule:

```text
show net PnL only
```

### 2. Activity And Leverage Are Different Decisions

100x can make PnL move quickly, but active markets also reduce reaction time and liquidation distance.

For slow BTC/ETH tape, 100x with normal fees can bleed the user even when the chart is moving slightly in their favor.

Product rule:

```text
activity chooses the market
loss budget and liquidation buffer choose the leverage
```

The admin defines allowed leverage buckets and hard caps per market and venue. The engine suggests from those buckets using ticket size, active collateral, recent stress movement, estimated costs, and the venue liquidation model. High leverage can remain available where allowed, but hot tape alone must never automatically increase it.

### 3. Volatility Scanner Is The Product

The app should not push every chart as tradeable.

The feed must answer:

```text
is this market moving enough right now to beat fees and still feel alive?
```

This is activity discovery, not a directional prediction. TICK can identify an active market with an acceptable route without claiming that long or short has positive expected return or that the movement will continue after entry.

If not, the UI should say the market is watching/waiting and should not fire a trade from a vertical swipe.

### 4. Opening And Closing Need Real State

Open and close are not instant UI events. They are real execution flows.

The app must show:

- Opening
- Live
- Closing
- Closed
- Failed / retry needed

The position must not disappear just because the close request was sent. It stops showing live exposure after authoritative venue close or liquidation confirmation. Final settlement and wallet/balance reconciliation can continue after that.

### 5. The Feed Must Not Switch By Itself

Users hated automatic switching. The feed can update rankings, but the active chart should not jump by itself while the user is watching.

Rules:

- Horizontal swipe changes market.
- Backend can update ranking in the background.
- Active chart stays active unless the user changes it.
- Pre-render next/previous charts so swipe feels instant.

## MVP Product Scope

### Mobile TICK

The local Expo MVP is the closest current expression of the intended product loop. The first deployable investor/team build may be a PWA for distribution speed, but it should copy the Expo interaction model instead of becoming a desktop trading terminal.

Mobile-shaped TICK launches with the main TICK product only.

No Pro mode on mobile at launch.

Core screens:

- Trade
- TICK dashboard
- Me

`Me` includes wallet, account, presets, limits, notifications, and settings.

`TICK dashboard` is not a boring account page. It is the volatility explorer summary:

- hot now
- markets watched
- recent trades
- best session
- alerts hit
- active-after-cost opportunities

### Web

Web can exist early, but it is not the main consumer product.

Web is useful for:

- internal testing
- farmers
- TICK Pro later
- route/venue debugging
- advanced metrics

Mobile is the product that can look and feel different from existing perp terminals.

### TICK Pro

TICK Pro is later.

It exposes:

- venue selection
- funding
- spread/depth
- leverage/margin controls
- route details
- execution quality
- advanced position management

Same backend, different frontend surface.

## Frontend Spec

### Stack

MVP UX reference:

- React Native
- TypeScript
- Expo is acceptable for mock/live MVP speed
- EAS/dev-client or bare React Native later if native wallet/session features require it

First deployable frontend:

- PWA-first is acceptable for fast sharing and Vercel deployment
- Mobile viewport and gestures remain the primary design target
- The PWA should use the same backend APIs as the native app

Web/TICK Pro:

- React/Next or Vite React is fine
- Should use the same backend APIs
- Pro UI can be separate from mobile UI

### Trade Screen

The main screen shows one market.

Required elements:

- TICK brand
- active symbol and asset name
- suggested leverage
- current price
- balance
- live chart
- right-side price axis
- current price label
- entry line after position opens
- net live PnL
- close button
- market state badge
- compact live execution terms before opening

Keep the main screen simple. The market badge and compact terms can show:

```text
HOT
MOVE 0.16% · COST 0.12%
```

Definitions:

- `MOVE`: recent observed movement over the active scanner window.
- `COST`: estimated underlying move needed to cover the all-in route cost.
- `activitySurplusPct`: internal value calculated as `MOVE - COST`.

Do not call this value `edge`: it does not predict direction or positive expected return. If `activitySurplusPct <= 0`, the screen should remain watchable but opening is disabled.

The compact execution terms are continuously refreshed and include the preset ticket, leverage, exposure, estimated all-in cost, collateral at risk, and liquidation estimate. They must be visible before the opening gesture without turning the screen into an order form.

### Gestures

Mobile gestures:

- no position: swipe up opens long
- no position: swipe down opens short
- live long: swipe up again closes
- live short: swipe down again closes
- swipe left: next market
- swipe right: previous market

The deliberate vertical swipe past the gesture threshold is the confirmation. There is no mandatory second tap, hold, or confirmation rail in the normal flow because the exact preset and live execution terms are already visible.

Opening swipes execute only against a valid short-lived preflight and only while the market is tradeable. If price, cost, leverage, balance, or venue health moves outside the preset tolerance, opening fails closed and the terms refresh.

Closing is different: it is never blocked by the scanner score or by activity cooling. The same-direction swipe closes the live position using the current close estimate and the user's close-slippage policy. If the venue itself cannot close, TICK must show the exact blocked or degraded state and keep reconciliation active. The opposite vertical swipe does not add to or reverse the position in V1. The visible `Close` button remains as a fallback.

With one concurrent position in V1, its market remains the active chart until the position closes. Horizontal market swipes are disabled during `Opening`, `Live`, and `Closing` so the second vertical swipe remains unambiguous.

Gestures are locked during `Opening` and `Closing`. A touch cannot emit twice, and every request remains idempotent on the backend.

If the market is not tradeable, vertical swipe flashes:

```text
WAIT
```

This prevents the app from encouraging bad trades in stale markets.

### PnL

The frontend must show net PnL.

Wrong:

```text
gross mark-to-entry movement
```

Correct:

```text
estimated or realized position result after venue costs
```

During an open position:

- use backend position state
- use current mark price
- subtract actual opening fee already incurred
- subtract estimated closing fee
- subtract estimated current price impact, spread, slippage, borrowing, and funding where applicable
- show the number as estimated until close confirms

Primary label:

```text
Est. net if closed now
```

Gross market movement may appear in the breakdown, but never as the apparent account result.

After close:

- calculate realized PnL from venue fills, price PnL, execution fees, funding, close/liquidation fees, and allocated venue costs
- use wallet and venue balance deltas as reconciliation checks, not as the per-trade PnL source
- distinguish consumed costs from locked or refundable reserves
- never show an optimistic green close before the close settles

### Chart

The chart should use real price data.

Allowed:

- choose a tighter/shorter visible time window
- smooth rendering
- right-side price axis
- dynamic y-axis around current price and entry
- highlight current price
- show volume/candle hints when useful

Not allowed:

- fake prices
- fake volatility
- stale chart movement that does not match real price

The chart can be visually exciting, but price must be real.

### Position UI

Position panel should show:

- entry
- current price
- ticket size
- estimated venue cost
- collateral at risk
- estimated liquidation
- close button

Button copy:

```text
Close
Closing
```

Avoid casino wording like `cash out` in the real product UI.

### Dashboard

Dashboard should rank markets by tradeability, not raw movement.

Scanner row should show:

- symbol
- asset class
- price
- move
- estimated cost hurdle
- activity surplus
- score meter

The scanner should make it obvious when the app found a real opportunity versus when the user is just watching.

## Backend Spec

### Stack

Use Python/FastAPI for V1.

This is acceptable because the first bottleneck is correctness, venue integration, state reconciliation, and product iteration, not raw API latency.

Recommended V1 stack:

- FastAPI
- Postgres
- Redis
- background worker process
- WebSocket/SSE for live position/feed updates when needed
- structured logs
- admin/operator scripts

Do not overbuild microservices in V1.

Start as a modular monolith:

```text
tick_backend/
  api/
  auth/
  wallets/
  balances/
  markets/
  scanner/
  routing/
  execution/
  venues/
  positions/
  reconciliation/
  notifications/
  audit/
  admin/
```

### Core Backend Modules

#### Auth And Wallets

Responsibilities:

- Google login for the current MVP
- user identity
- wallet mapping
- session permissions
- deposit/withdraw state
- versioned eligibility decisions

Current MVP decision:

- user signs in with Google
- backend issues a TICK session JWT
- backend creates a per-user Arbitrum wallet
- private key is encrypted before storage in Postgres using an env encryption key
- user deposits Arbitrum USDC to that wallet
- backend completes one-time gTrade delegation/allowance setup through workers
- normal gTrade opens/closes are signed by the TICK execution agent while the user wallet remains owner
- platform pays ETH gas and records actual USDC gas charges
- withdrawals remain signed by the user's platform-created wallet

Current implementation status:

- Arbitrum USDC withdrawal requests are persisted and serialized against active positions.
- The worker encrypts and persists the exact signed transaction before broadcast, then reuses the same bytes and hash during recovery.
- Confirmed withdrawals append a wallet-sourced ledger event.
- TICK automatically tops up low user wallets only when setup or withdrawal requires a user-wallet transaction. Normal delegated opens/closes spend agent ETH. Users only deposit and see USDC.
- Actual confirmed approval/open/close/withdrawal gas is converted through the Arbitrum Chainlink ETH/USD feed and reserved from spendable USDC in an idempotent ledger event keyed by transaction hash.
- Platform top-up overhead is absorbed by TICK. Reserved USDC treasury collection runs asynchronously and never blocks open or close.
- A process-wide nonce coordinator serializes all current senders across setup, delegated trading, top-ups, and withdrawals. V1 runs one execution worker; horizontal execution scaling requires agent sharding or a durable nonce lease.

This is simpler for a private MVP and investor demo because users do not need to understand wallets, ETH gas, delegates, or allowances. It also creates custody/security obligations, so it should not be described as production-grade public custody until signing isolation, withdrawal controls, revocation, limits, monitoring, and incident handling are hardened.

Local live canary used max allowance/delegation for speed. That is acceptable for founder/demo wallets only, not a broad-public default.

External users need:

- bounded allowance based on maximum permitted ticket plus explicit operational buffer
- delegated agent display
- allowance display
- revoke delegate
- revoke allowance
- disable trading
- server-side policy enforcement before every signature

An eligibility decision should record the policy version, user and location inputs required by the launch model, venue, market, leverage limit, result, reason, and expiry. V1 needs this decision boundary, not a large generic compliance engine.

#### TICK Balance

User sees one TICK balance.

Internally, funds may sit in:

- wallet idle USDC
- venue margin account
- pending deposit
- pending withdrawal
- locked position margin

V1 should not do real cross-venue margin.

The backend can manage wallet and venue pockets while showing one clean product balance.

For the current platform-wallet MVP, use an append-only money-movement journal and reconcile it to wallet and venue truth. A full double-entry ledger becomes mandatory before pooled custody, internal transfers, or a genuinely spendable cross-venue balance.

#### Market Data Normalizer

Normalizes:

- symbol
- asset class
- venue market id
- price
- bid/ask
- market open status
- max leverage
- fee schedule
- recent candles
- venue health

The app should never know venue-specific market ids.

#### Volatility Scanner

This is core product infrastructure.

Inputs:

- recent price movement
- active tape range
- realized volatility
- spread
- estimated slippage
- taker fees
- venue reserves or order costs
- max leverage
- market open status
- route reliability
- optional volume/open interest/liquidation data

Outputs:

```text
MarketOpportunity
  market
  assetClass
  price
  movePct
  activeTapePct
  feeHurdlePct
  activitySurplusPct
  feeCoverage
  tradability
  suggestedLeverage
  state: watching | cost_covered | hot_tape | cooling | closed
```

Definitions:

```text
activitySurplusPct = activeTapePct - feeHurdlePct
```

This measures activity remaining above estimated costs. It is not trading edge and contains no directional claim.

Opening should be allowed only when:

```text
activitySurplusPct > minimumSurplus
tradability >= threshold
price and route estimate are fresh
venue is healthy
market is open
user is eligible
```

The current local MVP threshold is intentionally simple:

```text
activitySurplusPct > 0 and tradability >= 24
```

Production should tune this with actual execution data.

For every scanner candidate, including candidates not shown to users, store the market snapshot, estimated route and cost, subsequent 30-second/1-minute/5-minute path, maximum favorable/adverse movement, actual quote-to-fill slippage, and failures. Shadow measurement runs alongside product development and does not block controlled live execution.

#### Cost And Leverage Engine

This engine estimates the real break-even hurdle for a trade.

It must include:

- open fee
- close fee
- spread cost
- slippage
- venue-specific reserves/order costs
- funding risk if hold may cross funding
- leverage
- ticket size

Output:

```text
CostDecision
  requestedLeverage
  suggestedLeverage
  maxVenueLeverage
  ticketUsd
  requestedCollateralUsd
  effectiveCollateralUsd
  requestedNotionalUsd
  effectiveNotionalUsd
  lossBudgetUsd
  activeCollateralUsd
  collateralAtRiskUsd
  estimatedOpenCostUsd
  estimatedCloseCostUsd
  estimatedRoundTripCostUsd
  dynamicPriceImpactUsd
  borrowingFeeUsd
  feeHurdlePct
  stressMovePct
  estimatedLiquidationPrice
  reason
```

The local tests showed why this matters:

```text
$20 at 100x can start with material cost/reserve drag.
$10 at 500x can start with roughly $1.85-$2.00 round-trip fee drag.
```

That means the scanner must find movement large enough to overcome that hurdle. Suggested leverage then comes from the user's loss budget and a safe liquidation buffer under recent stress movement, capped by user, policy, venue, liquidity, and admin limits.

#### Route Scorer

Route scoring order:

1. Eligibility
2. Market availability
3. Venue health
4. Estimated all-in cost
5. Liquidity/spread/slippage
6. Leverage fit
7. Reliability/reconciliation quality
8. Reward/points upside

Rewards are useful, but never above execution quality.

#### Execution Router

Before an opening swipe, the frontend keeps direction-specific short-lived execution preflights warm for the visible preset. This is a server-side executable estimate; it is only a firm quote when the venue actually provides one.

Creating or refreshing that preflight also schedules venue-neutral wallet
preparation. For the selected route this may warm the pending nonce, permission
state, gas inputs, and event correlation. Venue-specific permission mechanics
remain inside the connector.

```text
ExecutionPreflight
  quoteId
  userId
  market
  side
  ticketUsd
  requestedCollateralUsd
  effectiveCollateralUsd
  requestedNotionalUsd
  effectiveNotionalUsd
  leverage
  maxVenueLeverage
  estimatedOpenCostUsd
  estimatedCloseCostUsd
  estimatedRoundTripCostUsd
  dynamicPriceImpactUsd
  borrowingFeeUsd
  collateralAtRiskUsd
  estimatedLiquidationPrice
  quoteConfigVersion
  quoteSourceBlock
  route
  price
  priceTimestamp
  expiresAt
  eligibilityDecisionId
```

The opening request references that preflight instead of silently recomputing materially different terms.

```text
TradeIntent
  userId
  quoteId
  market
  side
  ticketUsd
  requestedLeverage
  lossBudgetUsd
  slippageLimit
  source
  idempotencyKey
```

The router:

1. validates the user preset and preflight expiry
2. rejects material price, cost, leverage, balance, or health changes
3. checks current market opportunity and eligibility decision
4. selects the approved route
5. creates execution plan
6. submits through venue adapter
7. waits for venue confirmation if requested
8. returns normalized position state

Every open/close must be idempotent.

Mobile retries must not create duplicate positions.

#### Venue Adapters

V1 should be venue-agnostic, even though the first live execution path uses gTrade/Gains.

Do not make a connector method own the whole lifecycle from "submit" to "normalized position state." The local canary proved the gTrade mechanics, but the production backend needs smaller venue primitives:

```text
VenueMarketData
  list_markets()
  get_market_config()
  get_price()
  get_history()

VenueQuoteEngine
  estimate_open()
  estimate_close()

VenueTransactionBuilder
  build_open()
  build_close()
  build_permission_setup()

VenueSubmitter
  submit_signed_transaction()

VenueEventDecoder
  decode_log()
  correlate_event()
  backfill_events()

VenueSnapshotReader
  get_positions()
  get_account()
  get_history()

VenueReconciler
  reconcile_execution()
  reconcile_position()
```

Adapter outputs must normalize the primitives TICK actually needs:

- available markets
- max leverage by market
- open fee, close fee, spread, price impact, borrowing/funding, and reserves
- expected open and close lifecycle latency
- position state source and confidence
- direct event/log availability
- wallet and venue balance reconciliation
- venue health and degraded modes

First venue priorities:

- gTrade/Gains: first live MVP execution route because the high-leverage,
  wallet-owned flow and mobile loop have been canary tested.
- Aster, Lighter, Pacifica, GMTrade, and Ostium: research or shadow adapters only until the first route is deterministic.

The architecture is venue-agnostic from the start, but only one venue executes initially. Enable a second live route only after every gTrade/Gains order, fee, balance movement, callback event, and position transition is explainable.

#### Position Engine

Do not mix user authorization, transaction attempts, economic exposure, and reconciliation into one state field.

TradeIntent states:

```text
created
validated
accepted
rejected
expired
cancelled
```

ExecutionAttempt states:

```text
created
signed
broadcast_pending
broadcast
initiation_confirmed
awaiting_venue_execution
venue_executed
failed
timed_out
unknown
reconciled
```

Position states:

```text
opening
open
closing
closed
liquidated
unknown
```

Reconciliation states:

```text
not_needed
pending
confirmed
recovered
mismatched
manual_review
```

The app should only show a position as live after venue confirmation.

The app should stop showing live exposure after authoritative close or liquidation confirmation. Settlement and final PnL can continue after that:

```text
Position = closed
Settlement = pending
```

Then finalize settlement after venue cash flows, trade history, and wallet/balance reconciliation are complete.

Workers and monitors append observations. They do not compete to mutate normalized position state.

Observation examples:

```text
transaction_signed
transaction_broadcast
receipt_observed
register_trade_observed
callback_log_observed
unregister_trade_observed
snapshot_present
snapshot_absent
balance_observed
deep_reorg_observed
```

A single reducer applies observations using versioned compare-and-swap transitions.

#### Reconciliation Worker

This is mandatory, not optional.

It watches:

- submitted orders
- venue order state
- venue position state
- wallet/venue balances
- stale opening/closing positions
- mismatches between TICK DB and venue truth

Normal finalization path:

```text
initiation transaction mined
-> direct callback execution log observed
-> position snapshot confirms result
-> venue cash-flow fields decoded
-> wallet balance reconciles
-> result final
```

Explicit recovery finalization path:

```text
callback log unavailable
+ repeated REST position absence
+ venue history indicates closure
+ wallet balance movement reconciles
-> recovered finalization
```

Recovered results must be marked with `finalization_source = recovered` and a `recovery_reason`.

#### Operational Safety Controls

Keep V1 controls small and enforceable:

- one concurrent position per user
- per-user ticket and session-loss caps
- market, venue, and global exposure caps
- stale-price and venue-health rejection for opening
- close-only mode
- market, venue, and global kill switches
- deadlines and operator alerts for stuck `opening`, `closing`, and `unknown` states

These are backend controls. The mobile client cannot override them.

#### Audit Log

Every trade action needs a durable audit record:

- user
- request payload
- preflight result
- route decision
- cost estimate
- venue request
- tx/order ids
- venue response
- fills, fees, funding, and reserve movements
- position state transitions
- balance before/after
- realized PnL
- errors/retries

This is needed for debugging, support, compliance, and route improvement.

## API Shape

Initial API:

```text
GET  /api/markets
GET  /api/markets/{market}
GET  /api/chart?market=BTC-USD&window=...
GET  /api/account
GET  /api/balance
GET  /api/positions
GET  /api/history
POST /api/trade/quote
POST /api/trade/open
POST /api/trade/close
POST /api/presets
GET  /api/presets
GET  /api/notifications/settings
POST /api/notifications/settings
```

Admin/operator:

```text
GET  /admin/venues
GET  /admin/routes
GET  /admin/trades/{id}
POST /admin/reconcile/{tradeId}
POST /admin/disable-market
POST /admin/disable-venue
POST /admin/close-only
POST /admin/halt-trading
```

Live updates:

```text
WS /stream/feed
WS /stream/positions
```

REST polling is acceptable for early MVP. WebSocket/SSE should be added once the flow is stable.

## Data Model

Minimum tables:

```text
users
wallets
user_presets
venues
venue_accounts
markets
market_snapshots
market_opportunities
route_quotes
trade_intents
execution_attempts
fills
fee_events
money_movements
positions
position_snapshots
balance_snapshots
transfers
eligibility_decisions
reward_programs
audit_events
notification_events
```

Keep all money values as decimals/integers, not floats.

`money_movements` is the append-only V1 journal. Do not infer individual trade results from a raw wallet balance delta.

`route_quotes` stores the direction-specific execution preflights and route estimates referenced by opening requests.

## Real MVP Build Order

### PR1: Quote And PnL Correctness

- keep the working gTrade/Gains behavior
- implement current venue cost model rather than simplified open fee math
- calculate requested collateral, effective collateral, requested notional, and effective notional
- model open fee, estimated close fee, price impact, spread, slippage, borrowing/funding, and liquidation
- persist immutable quote snapshots
- enforce quote TTL, price drift, cost drift, config version, and source block
- show estimated net result if closed now
- add tests around the live `$10 / 500x` economics

### PR2: Durable Execution Core

- FastAPI stays
- Postgres replaces SQLite for execution truth
- Redis can cache and broadcast live state, but cannot be required for money safety
- add migrations
- add durable job table or transactional outbox
- separate worker process
- bind idempotency key to canonical request hash
- return conflict when the same key is reused with a different payload
- make quote consumption unique
- compute and persist signed transaction hash before broadcast
- persist nonce, execution attempt, and raw signed transaction reference before RPC submission
- recover accepted-but-timeout RPC broadcasts by precomputed hash
- use versioned compare-and-swap state transitions
- enforce one active position and one active command with database constraints
- make quote consumption unique
- add a durable outbox/job table; Redis is a wake-up mechanism, not the source of financial truth

### PR3: Direct Logs, Event Journal, And Recovery

- pin exact deployed venue ABI/version
- parse direct open and close callback logs
- store raw and decoded logs with uniqueness on `chain_id`, `transaction_hash`, and `log_index`
- backfill from last trusted block after restart or reconnect
- handle duplicate logs idempotently
- handle `deepReorg` by rewinding and replaying affected observations
- use direct callback logs as the normal fast path
- keep the normalized Gains WebSocket as a fallback observation source
- replace unlimited WebSocket frames with measured bounded limits
- record compressed and decoded event sizes
- use exponential reconnect backoff with jitter
- run REST snapshot reconciliation after reconnect

### PR4: Security And Operator Controls

- one encrypted platform-created wallet per external private-beta user
- wallet ETH monitoring and controlled gas top-ups
- automatic max USDC allowance for the selected MVP venue
- allowance revocation and trading-disable endpoints
- one-position and one-in-flight-command enforcement at the database level
- user, market, venue, and global kill switches
- close-only mode
- server-side ticket, leverage, market, and loss policy checks
- operator timeline for every execution

### PR5: Failure-Injection Canary Certification

Run controlled real and simulated cycles before broader access:

```text
30-50 complete open/close cycles
zero duplicate transactions
zero false closed states
100% eventual reconciliation
successful backend-restart recovery
successful WebSocket-disconnect recovery
no unexplained PnL differences
callback transaction captured for normal executions
all transaction ambiguities resolved by deterministic hash
```

Inject:

```text
RPC timeout after transaction acceptance
backend restart while awaiting callback
WebSocket disconnect
duplicate WebSocket event
REST lag
callback arriving before receipt handling
duplicate close request
liquidation during close
balance mismatch
deep reorg signal
```

### Post-Core: Mobile App Hardening

- React Native app
- Trade screen
- Dashboard
- Me/account
- real backend APIs
- no fake PnL
- no fake chart prices
- open/close state handling
- same-direction swipe to close
- pre-render next/previous chart
- state updates around 200-250 ms where useful

### Post-Core: Second Venue Live Routing

Promote a shadow venue to selected live routing only after the gTrade/Gains route passes PR5.

Reason:

- forces real venue abstraction
- gives route alternative
- supports points/reward strategy where eligible
- prevents the product from becoming one venue's skin
- avoids doubling execution risk before reconciliation is proven

### Post-Core: Notifications And Retention

- volatility alerts
- watchlist alerts
- market moved alerts
- no advice-style alerts

Good:

```text
SOL volatility is live.
BTC moved -2.4% in 10 minutes.
ETH broke today's range.
```

Bad:

```text
Long SOL now.
Easy profit on BTC.
```

## MVP Non-Goals

Do not build in V1:

- own exchange
- own matching engine
- binary options
- pooled custody or internal exchange-style omnibus balances
- portfolio margin
- full social network
- copy trading
- complex options
- advanced TICK Pro terminal on mobile
- trade-count or volume rewards
- real-money PnL leaderboards

Engagement comes from real discovery, smooth gestures, haptics, live net PnL, and timely volatility alerts. It must not depend on fake movement or rewards for unnecessary turnover.

## Compliance And App Store Posture

Public framing:

```text
find the market moving now, see the real cost, and act in seconds
```

Avoid public framing:

- casino
- gambling
- betting
- guaranteed profit
- easy money
- play to win

The interface can be fast and engaging, but the trade terms must be clear:

- ticket size
- leverage
- exposure
- collateral at risk
- estimated liquidation
- estimated fees
- spread/slippage
- route
- market status

Only use `max loss` when the selected venue and instrument genuinely guarantee that bound. Before public real-money launch, the operating model must state the launch jurisdiction, eligible user classification, legal entity or licensed partner, instrument type, and approved venue. Prototype and shadow work can continue while that decision is made.

## Engineering Principle

Do not build a toy frontend over fragile execution.

The frontend can be simple. The backend cannot be sloppy.

Truth and speed are not opposing modes. TICK should maximize intensity inside real prices, visible terms, bounded presets, and confirmed execution state.

The real product only works if:

- the scanner is fee-aware
- PnL is net
- activity surplus is never presented as directional edge
- leverage follows loss budget and liquidation buffer, not market heat alone
- open/close state is honest
- duplicate swipes do not duplicate orders
- position state reconciles to venue truth
- balance changes are explainable
- venues are replaceable rails, not the product

## Open Decisions

These are the remaining product/architecture choices that should be settled before wider external testing:

- Custody boundary after the private MVP: keep platform-created wallets, move to embedded/self-custody, or support both.
- PWA versus native after the investor/team build: PWA is fastest to share, but Expo/native remains the best reference for gestures, haptics, and notifications.
- External 500x policy: internal/demo mode is allowed; broader user access needs explicit eligibility, native stops, and visible cost/liquidation terms.
- Custody/signing provider after the private MVP: preserve the same wallet repository boundary if platform-encrypted keys move to Privy, KMS-backed signing, or embedded self-custody.
- Allowance and revocation UX: founder/demo can use max allowance, but broader users need a clear permission screen and revocation path.
- Scanner gate strictness: whether demo mode can override tradeability checks, and how clearly that is separated from real-money production mode.
- First second venue: Lighter, Aster, Pacifica, GMTrade, or Ostium should remain shadow/research until the gTrade lifecycle passes canary certification.

## Current Decision

Use Python/FastAPI for V1.

Use the local Expo app as the mobile UX reference. The first deployable frontend can be a PWA if that is faster to share with teammates and investors, but it should preserve the Expo loop: one market, vertical open/close gestures, horizontal market switching, real chart, real net PnL.

Use gTrade/Gains on Arbitrum for the first live MVP route because the delegated, user-owned position model and mobile loop have been canary tested.

Run Aster, Lighter, Pacifica, GMTrade, and Ostium as research or shadow routes only. Promote a second route to selected live execution only after the gTrade/Gains lifecycle and accounting are fully explainable.

Keep 500x available for internal engineering/demo mode. External V1 defaults should use lower leverage buckets and explicit gates.

The first production-quality version should optimize for:

```text
real execution correctness
fee-aware volatility discovery
net-PnL mobile UX
one-gesture enter/watch/exit loop
fast iteration
venue abstraction
```
