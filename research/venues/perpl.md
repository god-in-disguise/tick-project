# Perpl

Snapshot: 2026-08-06.

Status: official docs researched; Monad RPC read-only probe completed; Perpl-specific on-chain activity is not yet attributable from the supplied RPC.

## Bottom Line

"Purple" is most likely Perpl. The partner description lines up with Perpl's public story: a Dragonfly-led `$9.25m` raise, a fully on-chain perpetual CLOB on Monad, and a product that can support delta-neutral/farming terminal strategies.

Perpl is interesting for TICK, but not as an immediate V1 execution venue until its live markets, liquidity, leverage, fees, contracts, and integration path are verified. Its design is more promising for fast execution than an oracle-keeper venue, while its current adoption evidence is still early and partly third-party reported.

## What It Is

- Fully on-chain perpetual futures exchange built on Monad.
- CLOB model with matching and settlement on-chain.
- Wallet-based UX: docs describe connecting a wallet, enabling trading through a gasless signature, depositing USDC on Monad, and placing orders.
- Monad is EVM-compatible, so it should fit Privy embedded EVM wallets in principle.
- Perpl positions itself around self-custody and no off-chain matching engine.
- The order book documents O(1) post and cancel operations, with O(N) matching.
- Documented order types include market, limit, stop, take-profit, IOC, FOK, and reduce-only.
- Initially, margin is isolated and initial margin can vary by market and position size.
- Mark price combines oracle and synthetic-perp logic and is used for PnL and liquidation.
- Funding is approximately hourly, based on Monad block count.

## Why It Matters For TICK

Strengths:

- Strong funding/backers for an early perp venue.
- New-venue upside and possible farming value.
- EVM/Monad should fit Privy better than Solana-only flows.
- On-chain CLOB is philosophically aligned with non-custodial execution.
- If Monad performs as advertised, latency could be much better than oracle-callback venues.
- Native order-book execution may let TICK observe a direct fill rather than waiting for a separate oracle callback.

Risks:

- New-chain risk: Monad liquidity, wallets, bridges, RPC, indexers, and user funding are all extra moving parts.
- Perpl docs do not yet answer the key TICK questions: max leverage, live markets, order API, latency, fees, account model, and builder/points terms.
- Fully on-chain CLOB can still be slower or more complex than Hyperliquid-style off-chain matching.
- Farming value is speculative until points/token rules are concrete.
- A third-party June 2026 report described roughly `$70m` monthly volume and `1,000+` users, while another public tracker showed roughly `$44m` 24-hour volume and `$10.5m` open interest. These are useful activity signals, not TICK-verified measurements.
- The Monad chain itself is active, but current chain-level TVL and fees are much smaller than mature perp venues. Monad activity may also be incentive-sensitive.
- The current Perpl frontend is version `1.61.18` and describes itself as gated beta. Its frontend also includes a restricted-territory check, so access and jurisdiction need to be verified before treating it as a general TICK route.

## Read-Only Monad Probe

The configured `MONAD_RPC_URL` responded with:

```text
chain_id:          143
client:            Monad/0.15.1
syncing:           false
sampled blocks:    93,631,248 -> 93,631,304
sample duration:   about 8 seconds
observed cadence:  about 7 blocks/second
recent tx counts:  6-31 per sampled block
```

This proves that the RPC is connected to a live Monad node. It does not prove Perpl activity. The current documentation review did not locate a canonical Perpl contract-address list or public volume endpoint, so the next on-chain probe must first identify the exchange and perpetual contract addresses. Until then, block transaction counts must not be presented as Perpl volume.

The live frontend exposes a public API-docs repository link, `https://github.com/PerplFoundation/api-docs`, but the deployed frontend still does not provide enough information to safely infer the exchange contracts from generic Monad traffic. The next probe should use the documented API or the Perpl team-provided addresses, then filter logs by those addresses.

## Activity Read

```text
Monad chain health:       live and advancing
Perpl public activity:    early but non-trivial reported activity
Perpl activity verified:  not yet
Perpl liquidity quality:  not yet
TICK canary readiness:    research only
```

The strongest evidence for Perpl is its protocol design and reported usage. The weakest evidence is independently verifiable fill quality for small, high-leverage orders. For TICK, the important measurement is not chain TPS. It is market-specific depth, fill probability, slippage, fee burden, and time from signed order to authoritative fill.

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
2. max leverage by market and current minimum order/margin
3. public API / SDK / contract addresses
4. whether external frontends can integrate trading
5. points, referral, builder, or grants program
6. whether session-key or delegated wallet execution is supported
7. expected order latency and gas per market order
8. current maker/taker fees, funding, and liquidation/insurance behavior
9. websocket or event source for order lifecycle and fills
10. current market-by-market depth and fill statistics
```

## Primary Sources

- [Perpl funding announcement](https://blog.perpl.xyz/announcing-our-9-25m-funding-led-by-dragonfly-capital/)
- [Perpl site](https://perpl.xyz/)
- [Trading perpetuals on Perpl](https://docs.perpl.xyz/resources/trading-perpetuals-on-perpl)
- [Perpl architecture](https://docs.perpl.xyz/exchange/architecture)
- [Perpl order book](https://docs.perpl.xyz/exchange/order-book)
- [Perpl on Monad](https://blog.perpl.xyz/what-is-monad/)
- [Perpl order types](https://docs.perpl.xyz/exchange/order-types)
- [Perpl margin](https://docs.perpl.xyz/exchange/margin)
- [Perpl liquidation](https://docs.perpl.xyz/exchange/liquidation)
- [Perpl price indices](https://docs.perpl.xyz/exchange/price-indices)
- [Perpl funding](https://docs.perpl.xyz/exchange/funding)
