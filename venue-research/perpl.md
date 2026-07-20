# Perpl

Snapshot: 2026-07-20.

Status: official docs and funding announcement researched; no TICK technical probe yet.

## Bottom Line

"Purple" is most likely Perpl. The partner description lines up with Perpl's public story: a Dragonfly-led `$9.25m` raise, a fully on-chain perpetual CLOB on Monad, and a product that can support delta-neutral/farming terminal strategies.

Perpl is interesting for TICK, but not as an immediate V1 execution venue unless Monad mainnet, liquidity, API/docs, and leverage are ready enough. It is more likely a farming/upside research venue than the first reliable mobile trading rail.

## What It Is

- Fully on-chain perpetual futures exchange built on Monad.
- CLOB model with matching and settlement on-chain.
- Wallet-based UX: docs describe connecting a wallet, enabling trading through a gasless signature, depositing USDC on Monad, and placing orders.
- Monad is EVM-compatible, so it should fit Privy embedded EVM wallets in principle.
- Perpl positions itself around self-custody and no off-chain matching engine.

## Why It Matters For TICK

Strengths:

- Strong funding/backers for an early perp venue.
- New-venue upside and possible farming value.
- EVM/Monad should fit Privy better than Solana-only flows.
- On-chain CLOB is philosophically aligned with non-custodial execution.
- If Monad performs as advertised, latency could be much better than oracle-callback venues.

Risks:

- New-chain risk: Monad liquidity, wallets, bridges, RPC, indexers, and user funding are all extra moving parts.
- Perpl docs do not yet answer the key TICK questions: max leverage, live markets, order API, latency, fees, account model, and builder/points terms.
- Fully on-chain CLOB can still be slower or more complex than Hyperliquid-style off-chain matching.
- Farming value is speculative until points/token rules are concrete.

## Current TICK Read

```text
Product rail today:        not accepted yet
Farming/upside candidate:  strong
Privy fit:                 likely, because Monad is EVM-compatible
100x fit:                  unknown
Integration priority:      research/contact, not build first
```

The right next step is to contact Perpl directly and ask for:

```text
1. current mainnet/testnet status
2. max leverage by market
3. public API / SDK / contract addresses
4. whether external frontends can integrate trading
5. points, referral, builder, or grants program
6. whether session-key or delegated wallet execution is supported
7. expected order latency and gas per market order
```

## Primary Sources

- [Perpl funding announcement](https://blog.perpl.xyz/announcing-our-9-25m-funding-led-by-dragonfly-capital/)
- [Perpl site](https://perpl.xyz/)
- [Trading perpetuals on Perpl](https://docs.perpl.xyz/resources/trading-perpetuals-on-perpl)
- [Perpl architecture](https://docs.perpl.xyz/exchange/architecture)
- [Perpl order book](https://docs.perpl.xyz/exchange/order-book)
- [Perpl on Monad](https://blog.perpl.xyz/what-is-monad/)
