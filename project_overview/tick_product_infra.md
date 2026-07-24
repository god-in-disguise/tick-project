# TICK Product And Infra Direction

TICK is a mobile-first day-trading app for catching live market movement.

The core use case is simple: the user has 2-10 minutes, the market is moving, and they want to take a side, watch the number move, and cash out.

TICK should not feel like a perp terminal, CEX dashboard, or venue aggregator. It should feel like a fast market-movement catcher: one live market, one decision, live PnL, clear exit.

The launch can be crypto-first, but the product should be designed as a cross-asset market feed. If venues support it, TICK can show BTC, ETH, high-beta stocks, indices, gold, oil, and FX in the same swipe flow. The user's mental model is not "which venue do I use?" It is "what is moving right now?"

## Product Thesis

Day trading is participation in volatility.

People do not open this kind of app because they want to manage complex derivatives infrastructure. They open it because something is happening:

- BTC is dumping
- SOL is ripping
- NVDA is squeezing
- gold is breaking out
- oil is reacting to news
- Nasdaq is moving after macro data
- the market is bleeding
- a big candle is forming
- liquidations are spiking
- they are bored and want to feel the market

TICK turns those moments into a simple mobile flow.

The promise:

> Open the app, see what is moving, take a side, watch live PnL, cash out.

The moat is the volatility explorer for day trading. TICK should not just show a feed of volatile assets. It should decide which moves are tradeable after liquidity, spread, fees, leverage limits, route quality, and user eligibility.

## Mobile Launch

Mobile launches with the main TICK product only.

There is no TICK Pro on mobile at launch. No venue selector, no order book, no complex terminal controls, and no exposed perp infrastructure.

The main screen should be:

- one active market
- live chart
- live price movement
- simple long/short action
- live PnL after entry
- clear cash-out button
- direct route to the next market

The trade is still real. Before execution, the app must clearly show the important terms:

- stake
- exposure/leverage
- liquidation or max loss
- estimated fees
- spread/slippage estimate
- funding note if relevant
- selected risk preset

The interface can feel fast and game-like, but the trade terms cannot be hidden.

## Position Model

TICK should not use fixed rounds as the core mechanic.

The stronger model is a live open position:

1. User chooses long or short.
2. Position opens.
3. PnL moves live.
4. User can cash out manually.
5. Position can liquidate if it goes badly.
6. If the trade runs hard, the user can keep watching and holding.

This preserves the day-trading fantasy: catching the move and letting it run.

Optional auto-close, inactivity rules, TP/SL, or safety rails can be added later, but they should not replace the core live-position experience.

For very short holds, the main cost is usually not time. It is opening and closing. Funding matters if the trade crosses a funding timestamp, but for a 30-60 second position the more important question is whether the expected move can overcome taker fees, spread, and slippage.

The router and UI should treat this as a first-class rule:

```text
round-trip fee as % of margin = 2 * taker fee * leverage
```

At 100x, even a small taker fee becomes visible as a percentage of the user's margin. That does not kill the product, but it means 100x should be reserved for low-cost routes and genuinely hot markets. For normal movement, 25x-50x may create a cleaner loop.

## Mobile Surfaces

The main TICK product does not mean the app has only one screen. It means the trading interface is simple.

Mobile should still include:

- Trade: the main market-movement screen
- Activity: trade history, wins/losses, fees, funding
- Wallet: TICK balance, deposits, withdrawals, available margin
- Dashboard: open exposure, past trades, stats
- Profile: settings, eligibility, notifications, risk limits

These surfaces should support the trading loop, not compete with it.

## Social Layer

Social should be ambient, not the center of the product.

The app should feel like the user is trading inside a live market crowd, without becoming a full social network.

Good first social primitives:

- "238 trading BTC now"
- long/short pressure
- anonymous entry and cash-out pulses
- small avatars or dots on the chart
- recent public actions if users opt in
- friends or public profiles later

The main object is still the moving price. Social makes the market feel alive.

## Notifications

Notifications are a major loop.

TICK should call users back when volatility appears, but should not send advice-style prompts.

Good notifications:

- "BTC moved -3.1% in 10 minutes."
- "SOL volatility is live."
- "ETH broke today's range."
- "Liquidations rising on BTC."
- "Gold volatility is live."
- "Nasdaq broke the morning range."

Bad notifications:

- "Short BTC now."
- "Easy profit on SOL."
- "Do not miss this pump."

The goal is to notify the user that a market moment is happening, then let the user decide.

## Web Product

Web can have the main TICK product too, but web is the better place to expose TICK Pro.

TICK Pro is for serious traders who want control:

- venue selection
- leverage and margin controls
- order types
- funding
- open interest
- depth and spread
- route and execution details
- account and venue balances
- advanced position management

TICK Pro does not need to launch first. It can start as internal infrastructure and become a user-facing web product later.

## Core Infra Principle

Build a serious trading engine underneath a simple consumer interface.

The main TICK product should not be toy infrastructure. It should be a constrained wrapper over the same engine that later powers TICK Pro.

The product split:

- Mobile TICK: simple consumer execution
- Web TICK: same simplified flow on desktop
- TICK Pro: advanced trader surface
- Core Engine: shared backend for all modes

## High-Level Architecture

```text
Mobile App / Web App
  |
  | account, feed, trade intent, position state
  v
TICK API
  |
  +-- Auth And Wallet Layer
  +-- TICK Balance Service
  +-- Market Data Normalizer
  +-- Volatility Scanner
  +-- Feed Engine
  +-- Risk Preset Engine
  +-- Cost And Leverage Engine
  +-- Execution Router
  +-- Position Engine
  +-- Venue Account Mapper
  +-- Reconciliation Worker
  +-- Notifications Engine
  +-- Social Presence Layer
  +-- Audit And Operator Tools
  |
  v
Venue Adapter Layer
  |
  +-- Aster
  +-- Lighter
  +-- Ostium / cross-asset venue
  +-- Other venues later
```

The app should never depend directly on a venue's API shape. The app talks to TICK. TICK talks to venues.

## Venue Strategy

Users should not think about Aster, Lighter, Hyperliquid, Ostium, or any other venue in the main TICK product.

Venues are internal rails. TICK chooses the right venue based on:

- market availability
- liquidity
- fees
- spread and slippage
- leverage limits
- execution quality
- uptime
- eligible jurisdictions
- reward or points upside
- asset class coverage

For the main TICK product, TICK can silently choose the best venue per market, user, cohort, or session. Live venue switching does not need to be exposed.

For TICK Pro, venue selection can be exposed later.

The first serious venue mix should not be one-provider only. Aster and Lighter are useful for crypto perps and points/reward upside. Ostium-style venues are interesting because they can make TICK feel broader than crypto by adding stocks, indices, commodities, and FX to the same market-moment feed.

Route choice should be fee-aware. A 100x trade on an expensive taker route can start with a meaningful drag on margin, while the same trade on a low-fee or zero-fee route can feel much cleaner. The app should not promise "cheap" execution unless the route actually supports it.

## TICK Balance

The user should see one TICK Balance.

Internally, the balance may be split across:

- wallet idle balance
- Aster margin balance
- Lighter margin balance
- pending deposits
- pending withdrawals
- locked margin in open positions

V1 should avoid true cross-venue margin. That is complex and unnecessary. The backend can manage venue pockets while the user sees a single product balance.

## Trading Intent

TICK owns the user intent model.

Main TICK trade intent:

```text
TradeIntent
  userId
  market
  assetClass
  side: long | short
  stakeUsd
  leverage
  maxLossUsd
  slippageLimit
  estimatedRoundTripCostUsd
  riskPreset
  source: mobile_tick | web_tick | tick_pro
```

The execution router turns this into venue-specific orders.

The important point: the frontend sends intent, not venue mechanics.

## Backend Responsibilities

The backend is the product engine.

It needs to:

- rank markets by current movement
- run the volatility explorer that finds tradeable day-trading moments
- normalize prices, markets, fees, leverage, and risk
- normalize asset classes and venue-specific market names
- generate the live feed
- validate user eligibility and risk limits
- choose leverage based on market state, route cost, and user preset
- convert simple trade intent into venue execution
- prevent duplicate orders and retry mistakes
- track live positions and PnL
- reconcile venue state against TICK state
- manage user-visible balance
- send volatility notifications
- keep a full audit trail
- support operator recovery tools

The hard part is not placing an order. The hard part is staying correct when real money, mobile sessions, venue latency, partial failures, and fast prices are involved.

## MVP Direction

First version should stay narrow:

- mobile TICK first
- at least two venues behind the scenes
- limited but varied market universe
- simple long/short market orders
- isolated margin only
- no venue selector
- live PnL and cash-out
- wallet/account/history/dashboard
- volatility alerts
- anonymous crowd presence
- strong reconciliation and audit logs

The first product should prove that the loop works:

> market moves -> TICK alerts -> user opens app -> takes side -> watches live PnL -> cashes out -> returns next time volatility appears.

## Public Framing

Public framing should be day trading and market alerts, not casino.

Good framing:

> TICK is a mobile trading app for eligible users who want to react to live market volatility with a simple long/short interface and clear trade terms.

Avoid public wording like:

- casino
- gambling
- betting
- binary options
- guaranteed profit
- play to win
- easy money
- advice-style alerts

The product can use fast feedback, live movement, and social presence internally, but the external framing should stay in the trading and market-alert category.
