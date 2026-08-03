# Orderly

Snapshot: 2026-08-03.

Evidence: documented and public measured; not live tested by TICK.

## Bottom Line

Orderly is the clearest infrastructure-level fit for TICK's venue-agnostic
architecture. It is designed for builders that own the frontend and user
relationship while using shared liquidity and normalized order APIs.

Its base fees make it better suited to moderate leverage and larger collateral
than the current $10 at 500x loop.

## Public Snapshot

TICK queried Orderly's public market endpoint on 2026-08-03:

```text
markets returned: 136
BTC/ETH/SOL minimum notional: $10
documented maximum leverage for BTC/ETH/SOL: 100x
base taker fee: 3 bps
```

At 3 bps on both sides:

```text
50x round-trip explicit fee drag: 3% of collateral
100x round-trip explicit fee drag: 6% of collateral
```

## Integration Fit

- REST plus public and private WebSocket APIs.
- Ed25519 Orderly trading keys with scoped permissions and expiration.
- Client and order identifiers suitable for idempotent execution.
- Native algorithmic TP/SL orders.
- Builder-controlled fees and a documented broker/builder model.
- Multi-chain collateral/account onboarding behind one order layer.

## Main Risks

- Builder onboarding and account registration must be implemented correctly.
- Shared order-book execution can introduce slippage on small or thin markets.
- Adding a builder fee would directly weaken TICK's activity-to-cost metric.
- A public endpoint does not prove signed order acknowledgement or fill latency.

## Best TICK Role

Orderly is a strategic route for a multi-venue web terminal and a normalized
crypto connector. It should be tested at 25x-100x with explicit quote depth,
not positioned as a replacement for gTrade's 500x degen loop.

## Primary Sources

- [Building on Orderly](https://orderly.network/docs/build-on-omnichain/building-on-omnichain)
- [Wallet authentication](https://orderly.network/docs/build-on-omnichain/user-flows/wallet-authentication)
- [API authentication](https://orderly.network/docs/build-on-omnichain/api-authentication)
- [Trading fees](https://orderly.network/docs/introduction/trade-on-orderly/trading-basics/trading-fees)
- [Create algo order](https://orderly.network/docs/build-on-omnichain/restful-api/private/create-algo-order)

