# TICK Market Feed Trading App

We are building a mobile-first high-velocity trading app that finds volatile markets for the user and lets them act in one gesture.

Most CEX apps are still dashboards. They give the user hundreds of pairs, too many tabs, and no clear answer to the basic question: what is moving right now? TICK turns that into a feed. The user does not hunt through markets; the app ranks live opportunities by volatility, volume, liquidity, spread, momentum, execution quality, and all-in trading cost.

The main TICK product is built for retail day traders. One chart, one market, one clear action. Swipe up to prepare a long, swipe down to prepare a short, swipe sideways to move to the next market. Before execution, the user sees the actual trade terms: size, leverage, liquidation or max loss, estimated fees, spread/slippage, and the active risk preset. It feels fast, but it is still real trading.

TICK Pro is the same engine with the full cockpit exposed. Traders get funding, open interest, volume, order book depth, mark/index spread, liquidation risk, position controls, bracket orders, reduce-only, and fast mobile execution. The goal is not to dumb trading down for pros; it is to make serious perp trading usable from a phone.

The first market universe can be crypto-first, but the bigger feed is cross-asset: BTC, ETH, high-beta stocks, indices, gold, oil, and FX when compliant venues support them. Products like Ostium make this strategically interesting because TICK can become the front end for "what is moving now" across crypto and macro, not only another crypto pair list.

TICK should not become one venue's skin. Users see one clean product balance and one trade flow, while the backend is written in venue-agnostic primitives from the beginning. The first live MVP route is gTrade/Gains until execution is fully explainable; other venues can run as research or shadow checks before becoming live routes.

The moat is the volatility explorer for day trading. TICK should know what is moving, how cleanly it can be traded, what leverage makes sense, and when the move is worth pushing to the user. The swipe UI is the surface; the volatility explorer is the engine.

Leverage should be dynamic. The exciting range is roughly 25x-100x, but 100x only makes sense when the route is low-cost and the market is truly moving. At high leverage, opening and closing fees are amplified by the leverage multiplier, so the router must prefer low-fee venues and show cost before execution.

The product is finance-native, not a disguised casino. The entertainment layer comes from speed, market motion, ranking, streaks, and clean feedback. The trust layer comes from transparent risk, proper venue access, regional gating, and execution data.

The core promise:

Find the market that is moving. Show what it costs. Let the user trade it fast.
