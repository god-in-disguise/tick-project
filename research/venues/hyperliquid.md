# Hyperliquid

Snapshot: 2026-08-03.

Evidence: documented and public measured; not live tested by TICK.

## Bottom Line

Hyperliquid is a strong serious-crypto route, not the best extreme-leverage
small-ticket route. Its strengths are liquidity, broad crypto coverage, agent
wallets, deterministic order APIs, native trigger orders, and rich private
events.

## Public Snapshot

TICK queried `metaAndAssetCtxs` on 2026-08-03:

```text
perpetual markets: 232
BTC maximum leverage: 40x
ETH maximum leverage: 25x
SOL maximum leverage: 20x
HYPE maximum leverage: 10x
```

The public schedule lists a 4.5 bps base perpetual taker fee before volume and
staking discounts. At base fee:

```text
BTC 40x round-trip explicit fee drag: 3.6% of collateral
ETH 25x round-trip explicit fee drag: 2.25%
SOL 20x round-trip explicit fee drag: 1.8%
HYPE 10x round-trip explicit fee drag: 0.9%
```

## Integration Fit

- Agent/API wallets can trade for a master account without holding withdrawal
  authority.
- Official guidance recommends a separate API wallet per process or
  subaccount to simplify nonce handling.
- REST exchange actions and private WebSocket subscriptions cover orders,
  fills, funding, user events, and liquidations.
- Native stop-market, stop-limit, take-profit, and bracket-style grouping are
  available.
- Builder codes support product attribution and optional builder fees.
- Minimum order notional is $10 for the relevant perpetual path.

## Main Risks

- Maximum leverage is below TICK's current 100x-500x spectacle.
- Taker fees become visible when collateral is small and leverage is high.
- Builder fees would worsen the cost hurdle and should remain zero during
  route validation.
- Account/subaccount collateral flow differs from the current wallet-owned
  gTrade model.

## Best TICK Role

Use Hyperliquid for larger collateral and 10x-40x crypto presets where
liquidity, API truth, and execution quality matter more than maximum leverage.
It is a natural future route for the web terminal and TICK Engine API.

## Primary Sources

- [Trading fees](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees)
- [API wallets and nonces](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/nonces-and-api-wallets)
- [Order types](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/order-types)
- [WebSocket subscriptions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions)
- [Builder codes](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/builder-codes)

