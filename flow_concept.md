# TICK Market Arcade

The product is a mobile-first day-trading app built around speed, volatility, and simple decisions.

Most trading apps feel like dashboards. They show too many pairs, too many tabs, and too much noise. TICK turns trading into a live market arcade: one market at a time, ranked by what is moving right now.

The user opens the app and lands directly inside the action. A chart is live. The market is either cold, warming up, or on fire. The user can skip to the next market, go long, or go short from the same screen.

The first version can be crypto-first, but the bigger product is not limited to crypto pairs. The feed can include BTC, ETH, high-beta stocks, indices, gold, oil, and FX when the execution venue supports those markets. The point is not "more assets." The point is that TICK becomes the fastest way to feel the market when something is moving anywhere.

The product should not depend on one venue. TICK should feel like one clean app, but the backend should route through at least two execution venues from the start. Aster, Lighter, and Ostium-style venues are rails, not the product.

The moat is the volatility explorer for day trading. TICK should not only show charts. It should discover which markets are alive, rank whether the move is tradeable after fees and spread, choose a sensible leverage range, and call users back when a real market moment appears.

## Main TICK Product

The main TICK product is for retail users who want fast market action without a full trading terminal.

The user configures the trade style before entering the feed: default size, leverage range, max loss, TP/SL or manual cash-out preference, and margin mode. After that, the app becomes extremely simple. Every market uses the active preset unless the user changes it.

The screen is simple:

- One live chart
- One asset
- One direction decision
- Swipe sideways to skip
- Swipe up to long with the active preset
- Swipe down to short with the active preset

The trade terms stay visible on the screen: size, leverage, liquidation or max loss, estimated fees, spread/slippage, and exit rules. The user does not need to rebuild the ticket every time. The interface can feel like a game, but the trade is still clear.

The casino-style mechanics are in the pacing and feedback:

- Hot and cold markets
- Streaks
- Fast rounds
- Cash-out moments
- Trade result cards
- Daily leaderboards
- Fire markets
- Trial mode
- Small challenges
- Visual wins and losses

The feel is direct: preset risk, live market, one gesture, instant outcome, next market.

## Leverage And Cost

The product should feel fast, but the leverage cannot be dumb.

The useful main product range is roughly 25x-100x. 25x is more forgiving, 50x feels fast, and 100x creates the strongest live-PnL loop. But high leverage amplifies trading cost. A fee that looks tiny on notional can become meaningful as a percentage of the user's margin after opening and closing.

The rule:

```text
round-trip fee as % of margin = 2 * taker fee * leverage
```

This means 100x should be reserved for hot markets and low-cost routes. If the market is slow or the route is expensive, TICK should lower the suggested leverage or warn the user that fees/spread will eat the move.

## TICK Pro

TICK Pro is for real perp traders who want the same feed, but with the full trading cockpit.

It exposes venue, funding, open interest, volume, order book depth, spread, mark/index price, liquidation risk, position margin, TP/SL, reduce-only, brackets, execution cost, and rewards/points eligibility.

TICK Pro should not feel playful. It should feel fast, dense, and serious. The value for pros is not the arcade layer. The value is that the app finds tradeable markets quickly and lets them execute from mobile without losing control.

## The Core Loop

1. Open the app.
2. See the market moving now.
3. Decide: skip, watch, long, or short.
4. Swipe to trade with the active preset or move on.
5. See the result instantly.
6. Continue to the next market.

The product is built around momentum. The feed replaces the exchange dashboard. The market card replaces the slot. The trade result replaces the spin outcome.

## The Bigger Idea

Day trading is already a real consumer behavior. Robinhood proved that trading can become a mobile-first habit when the interface removes enough friction. Crypto perps are the higher-velocity version: 24/7 markets, faster moves, leverage, and constant volatility. Cross-asset perps and synthetic venues can extend that same behavior into stocks, indices, commodities, and FX.

The app is built for the moments when the user has 5-10 minutes and wants to feel the market. They do not need to open a full CEX terminal, search pairs, check scanners, and build a ticket. The app brings them straight into live market flow.

Social elements still matter, but they are not the center. Trade cards, leaderboards, and shared PnL make the experience more alive. The core product is simpler: open the app, feel what is moving, take a fast trade, move on.

Best one-liner:

> A mobile trading arcade for whatever market is moving now.
