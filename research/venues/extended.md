# Extended

Snapshot: 2026-08-03.

Evidence: documented and public measured; not live tested by TICK.

## Bottom Line

Extended is the strongest newly found cross-asset CLOB candidate. It exposes a
large market catalog through REST and WebSocket APIs, with lower headline
taker fees and a faster execution model than TICK's current oracle-style
cross-asset route.

## Public Snapshot

TICK queried the official market endpoint on 2026-08-03:

```text
products returned: 341
perpetual products: 338
BTC/ETH/SOL maximum leverage: 50x
XAU maximum leverage: 25x
EUR/USD maximum leverage: 100x
base taker fee: 2.5 bps
base maker fee: 0
```

At 2.5 bps on both sides:

```text
50x round-trip explicit fee drag: 2.5% of collateral
100x round-trip explicit fee drag: 5% of collateral
```

The market catalog includes crypto, equities, commodities, indices, and FX.
Leverage, trading hours, order increments, and liquidity vary materially by
product.

## Integration Fit

- REST and WebSocket APIs with API keys and Stark signatures.
- External order IDs support idempotent request correlation.
- Private order, fill, account, and position streams.
- Native TP/SL and conditional order support.
- Builder codes are documented.
- Public market metadata exposes trading hours and off-hours status for RWAs.

## Main Risks

- Stark account onboarding and signing add a new custody/account model.
- The number of listed products does not imply usable depth.
- Some RWA products use RFQ or restricted trading hours.
- Minimum order sizes are base-asset quantities and must be converted into a
  live minimum notional before the UI enables a preset.

## Best TICK Role

Use Extended as the first candidate for a broad pro/cross-asset route. TICK
Engine can discover from a wider data universe, then mark a route AVAILABLE
only when the specific Extended market has depth, open trading hours, and an
acceptable all-in quote.

## Primary Sources

- [Extended API](https://api.docs.extended.exchange/)
- [Trading fees](https://docs.extended.exchange/extended-resources/trading/trading-fees-and-rebates)
- [Builder codes](https://docs.extended.exchange/extended-resources/builder-codes)
- [Extended documentation](https://docs.extended.exchange/)

