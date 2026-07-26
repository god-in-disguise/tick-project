# TICK Mobile Mockup

React Native / Expo mockup for the main TICK mobile experience.

The mockup focuses on:

- market-moment feed
- volatility explorer presentation loop
- cross-asset presentation cards: crypto, stocks, indices, commodities, FX
- live moving chart
- asset-specific chart color and volatility personality
- simple direction execution
- live PnL and close
- preset-driven leverage and trade terms before execution
- wallet, activity, profile surfaces
- ambient crowd presence on the chart

It does not connect to real wallets or trading APIs.

The mockup is intentionally venue-agnostic. In the real product, the main TICK product should hide venue complexity while the backend starts with one explainable live route and keeps other venues as shadow/research rails until they are ready. The point of the demo is the volatility explorer, feed, and fast close loop, not a dependency on Aster, Lighter, Ostium, or any single venue.

## Run

```bash
npm install
npm run start
```

For browser preview:

```bash
npm run web
```
