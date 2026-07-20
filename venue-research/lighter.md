# Lighter

Snapshot: 2026-07-20.

Status: official documentation and public API researched; no TICK signed trade yet.

## Bottom Line

Lighter is a strong prototype candidate because its Standard account currently combines zero maker/taker fees with a deterministic 300 ms taker delay. The leverage is lower than Aster 1001x or GMTrade, but the execution model is much closer to the snappy investor demo TICK needs. It still needs a signed canary to measure spread, slippage, fill reliability, API-to-position latency, and account reconciliation.

## How It Works

- An Ethereum wallet registers the main Lighter account.
- Each account or subaccount can register API keys that sign exchange requests.
- An off-chain sequencer provides order-book execution and soft finality.
- Lighter generates ZK proofs and posts reconstructable state data to Ethereum.
- An on-chain priority queue and escape-hatch design exists for critical exits.
- Crypto markets support isolated positions; allocated margin is tracked separately from the rest of the account.

This gives TICK a fast API path without making Ethereum block time part of every normal order acknowledgement.

## Leverage And Cost

Current documented examples:

```text
BTC  50x
ETH  50x
SOL  25x
XRP  20x
HYPE 20x
BNB  20x
```

Live public API snapshot on 2026-07-20:

```text
Active perp markets: 201
Active spot markets: 7
Minimum quote size on selected perps: $10
Displayed maker/taker fees on selected Standard perp markets: 0.0000 / 0.0000

Selected live markets:
BTC       50x   ~$490M 24h quote volume
ETH       50x   ~$244M 24h quote volume
SOL       25x   ~$24M 24h quote volume
XAU       25x   ~$22M 24h quote volume
WTI       20x   ~$5.3M 24h quote volume
BRENTOIL  20x   ~$5.2M 24h quote volume
NVDA      20x   ~$1.1M 24h quote volume
SPY       50x   ~$0.5M 24h quote volume
QQQ       30x   ~$0.5M 24h quote volume
US500     50x   ~$0.4M 24h quote volume
```

Current account choices:

```text
Standard: 0 maker / 0 taker, 300 ms taker delay
Premium:  0.0040% maker / 0.0280% taker at zero LIT stake,
          200 ms taker delay, improving with LIT staking
```

For the TICK loop, Standard may be economically better even though it is 100 ms slower. At 50x, two 2.8 bps Premium taker fills equal roughly 2.8% of margin before other costs; Standard removes that explicit fee hurdle. This must be compared against real fill quality and rate limits.

## Points

Lighter documents Season 2 with 200,000 retail points distributed weekly. Organic trading quality and market weighting matter; API activity can qualify, while manipulation and sybil behavior are excluded. Premium account status can affect weighting.

Lighter already has the LIT token in its current fee/staking model. Do not frame its points as guaranteed pre-TGE upside.

## TICK Fit

Strengths:

- Low explicit cost for Standard accounts.
- Predictable documented delay rather than a multi-transaction oracle callback.
- API keys and subaccounts fit a connector architecture.
- BTC and ETH support 50x; enough for a fast loop if volatility selection works.
- Broad live market set gives the feed real variety across crypto, commodities, equities, indices, and FX-style products.
- Event-driven API should support honest opening/open/closing states.

Risks and unknowns:

- No 100x BTC/ETH.
- Standard-account rate limits and 300 ms delay need live testing.
- Zero fee does not mean zero spread, slippage, funding, or liquidation cost.
- Ethereum onboarding and deposit UX differ from Pacifica's Solana flow.
- Isolated margin is documented, but its API operations and account-state event semantics need connector-level verification.
- Regional eligibility and app-distribution constraints remain product-level gates.

## Next Test

1. Record public market, book, and trade-stream latency.
2. Create a dedicated test subaccount and API key.
3. Open a small BTC isolated position on Standard.
4. Close reduce-only after fill confirmation.
5. Repeat on ETH/SOL only if BTC lifecycle is clean.
6. Compare all-in cost and visible open/close latency directly with Ostium and GMTrade.

## Primary Sources

- [API and API keys](https://docs.lighter.xyz/perpetual-futures/api)
- [Technical architecture](https://docs.lighter.xyz/about-lighter/technical-architecture-lighter-core)
- [Trading fees and latency](https://docs.lighter.xyz/trading/trading-fees)
- [Contract specifications](https://docs.lighter.xyz/perpetual-futures/contract-specifications)
- [Liquidation and isolated-margin model](https://docs.lighter.xyz/perpetual-futures/liquidations-and-insurance-fund)
- [Points program](https://docs.lighter.xyz/points-program)
- [Retail points](https://docs.lighter.xyz/points-program/retail)
