# TICK Venue Research

This directory keeps venue knowledge separate from product specs and connector code.

- Product decisions live in `tick_real_build_spec.md`.
- Executable probes live in `research/experiments/venue-checks/`.
- Venue facts, measurements, and open questions live here.

Every venue page is dated because fees, leverage, APIs, rewards, and access rules change. Do not treat a points program as guaranteed token value, or an official performance claim as a TICK measurement.

## Evidence Labels

- **Documented:** confirmed in current official documentation or a public API.
- **Public measured:** measured by TICK against public endpoints, without signing or funds.
- **Live tested:** measured with a signed real-money order.
- **Unknown:** must be verified before a production decision.

## Working Matrix

Snapshot: 2026-08-08.

| Venue | Evidence | Best TICK use | Execution model | Useful leverage | Baseline trading cost | Rewards | Current view |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [Flash Trade](flash.md) | Live tested, shadowed | Future game-like high-leverage mode and execution research | MagicBlock ER with transaction builders, session keys, signed submission, and owner WS | BTC/ETH 100x and 500x live-tested; XAU 100x canary passed; SOL and synthetic 200x disabled | Live `$10 x 500` cycles cost about `$1.67`; positive PnL is reference-capped during the market-specific delay window | Voltage points exist; not a routing reason | Preserved as a shadow adapter; disabled as a production user route because its delayed positive-PnL mechanics do not match canonical perps |
| [Avantis](avantis.md) | Documented | Small-ticket high leverage and cross-asset | Base transaction plus oracle execution; SDK and delegation | ZFP majors documented at 75x-500x | ZFP has no fixed open/close fee; winning closes pay variable profit share; spread and execution still apply | Avantis XP exists; not a routing reason | Strongest new high-leverage canary candidate |
| [Ondo Perps](ondo.md) | Documented + public measured | TICK Pro and lower-leverage cross-asset | Offchain SGX order book/account engine with onchain deposits and withdrawals | 5x-25x across 35 enabled crypto, stock, ETF, index, and commodity markets | Live API reports 1.5 bps maker and 3.5 bps taker; liquidation can charge 1.5% of notional | Ondo points exist; not a routing reason | High-priority normal-wallet canary; rich data and fast matching, but cross-margin omnibus custody requires a distinct truth model |
| [Paradex](paradex.md) | Documented + public measured | Small-ticket crypto | Starknet CLOB with EVM onboarding and trading subkeys | BTC/ETH/SOL 50x, HYPE 20x in current public config | Interactive retail orders are zero fee with a 300 ms speed bump | Rewards are secondary | Strong immediate canary if TICK qualifies for interactive classification |
| [Aark](aark.md) | Live tested | Small-ticket high-leverage crypto | Gasless API/relayer with per-user delegated signer and venue balance | BTC 500x/750x/1000x in current live config | 1 bp open fee plus $0.60 execution fee in the live canary; losing close charged no trading fee | Existing AARK/VIP programs; not a routing reason | Full round trip works with Aark-origin challenge and live EIP-712 signing; TICK-origin challenges and documented EIP-191 opens are currently rejected |
| [GMTrade](gmtrade.md) | Live tested | High-leverage crypto and cross-asset feed | Solana order transaction followed by keeper/oracle execution; pool based | Live BTC 500x, ETH ~294x, SOL 250x; 54 markets at 100x+ | Crypto/stock/commodity: 1.0-1.2 bps per fill | GT points explicitly qualify users for its TGE | Public keeper path too slow; viable only with private/order-keeper lane |
| [Perpl](perpl.md) | Documented | Farming/upside research venue | Fully on-chain CLOB perps on Monad | Unknown from current docs | Unknown from current docs | Likely early-stage upside; exact points/builder program needs confirmation | Likely what partner meant by "Purple"; worth contacting, not accepted as execution rail yet |
| [Pacifica](pacifica.md) | Public measured | Fast crypto execution | Hybrid off-chain CLOB on Solana; signed REST/WS | BTC/ETH 50x, SOL 20x | Tier-1 taker 4 bps per fill | 10M points weekly; builder program | Viable 50x fallback; fee drag puts it behind zero-fee canary routes for $10 tickets |
| [Lighter](lighter.md) | Documented + public measured | Fast prototype route | Off-chain sequencer with ZK settlement on Ethereum | BTC/ETH 50x, SOL 25x; selected RWAs/indices 20-50x | Standard account: zero maker/taker, 300 ms taker delay | Season 2 points, but not the core reason to use it | Top signed-canary candidate alongside Paradex and Avantis |
| [Hyperliquid](hyperliquid.md) | Documented + public measured | Serious crypto and future pro terminal | HyperCore CLOB with agent/API wallets | BTC 40x, ETH 25x, SOL 20x, HYPE 10x in current config | Base taker 4.5 bps before discounts | Points are not the route thesis | Strong API/liquidity route at moderate leverage, not a 500x replacement |
| [Orderly](orderly.md) | Documented + public measured | White-label crypto routing | Shared CLOB infrastructure with broker-owned UX and trading keys | BTC/ETH/SOL documented up to 100x | Base taker 3 bps; optional builder fee | Secondary | Strong strategic architecture fit; requires builder onboarding and signed canary |
| [Extended](extended.md) | Documented + public measured | Cross-asset and lower-leverage pro | Starknet CLOB/RFQ with REST, WS, and API keys | Crypto majors 50x, XAU 25x, EUR/USD 100x in current config | 2.5 bps taker, zero maker | Secondary | Best newly found broad cross-asset API candidate |
| [Aster](aster.md) | Documented + public measured | Higher leverage, liquidity, points | Aster Perpetuals V3 API-agent path; separate 1001x direct-contract path on BNB/Arbitrum | Perps market-specific; Arbitrum 1001x config returned 500BTC at 1000x, BTC/ETH at 250x | Perps docs show 4 bps taker; 1001x live config returned $0.20-$0.50 execution fee and zero open fee on tested high-leverage pairs | Stage 6 points; Aster Code builder fees | V3 is usable API route; 1001x wallet route is currently reduce-only, so opens are blocked |
| [gTrade / Gains](gtrade.md) | Live tested | First live MVP route | Arbitrum direct contract or delegated trading, oracle fulfillment | Forex 1000x, degen crypto 500x, BTC/ETH 200x, commodities 250x | Pair-specific; live backend exposes fee groups and minimum notional | Credits/revenue programs exist, but not core for TICK | Selected first rail; harden execution, PnL, stops, events, and reconciliation before adding second live venue |
| [Ostium](ostium.md) | Live tested | Stocks, indices, commodities, FX | Arbitrum transaction plus oracle callback | Pair-specific, up to 200x | 3-10 bps open plus oracle and possible early-close cost | Points/rewards need current verification | Keep for cross-asset; weak first crypto rail |
| [Variational Omni](variational.md) | Documented | Future broad RFQ route | Gasless Arbitrum account with off-chain RFQ | Up to 50x | Zero explicit trading fee; spread-priced | Secondary | Attractive future route; public trading API is not available yet |

Costs above are venue schedules, not all-in TICK costs. Spread, slippage, funding or rollover, builder fees, gas, reserves, and liquidation mechanics still apply.

## Current Test Order

1. Harden the gTrade live route inside `builds/tick-mvp/`: quote truth, native stop, direct events, reducer, reconciliation, and deterministic transaction recovery.
2. Complete the Avantis ZFP benchmark with a profitable close, delegated lifecycle canary, guaranteed stop, and at least 20 optimized cycles.
3. Run an Ondo normal-wallet canary: SIWE, Arbitrum USDC deposit, 20x crypto cycle, 25x XAU cycle, private fills, withdrawal, and credential-scope verification.
4. Run a Paradex Retail signed canary and verify interactive classification, effective fees, the 300 ms speed bump, and private-event latency.
5. Run Lighter Standard in the same signed harness as Paradex.
6. Probe Hyperliquid and Orderly as moderate-leverage serious-crypto routes.
7. Probe Extended for crypto plus one RWA/FX market and measure depth, trading-hour behavior, signing, and fill lifecycle.
8. Continue Aark partner authorization; the live route works only with an accepted Aark-origin challenge today.
9. Keep Pacifica as a 50x fallback candidate and Ostium as the live-tested cross-asset accounting benchmark.
10. Keep Flash in shadow mode for future game mechanics and protocol research; do not expose it as a canonical perp route.

The full lane analysis and normalized cost formula are in
[`router-rescreen-2026-08-03.md`](router-rescreen-2026-08-03.md).
The Solana-specific comparison and Flash canary plan are in
[`solana-perps-rescreen-2026-08-04.md`](solana-perps-rescreen-2026-08-04.md).

This is a research order, not a final routing decision. Production routing should be chosen from measured fill latency, all-in cost, state consistency, market coverage, user eligibility, and operational control. Points are secondary.

The broader venue universe and triage list is in [`universe-2026-08-06.md`](universe-2026-08-06.md). It includes protocols that still require verification and must not be treated as live TICK candidates.

## Required Canary Output

Every signed venue test should record the same fields:

```text
request_to_ack_ms
ack_to_fill_ms
request_to_position_visible_ms
close_request_to_ack_ms
close_ack_to_fill_ms
close_request_to_position_gone_ms
quoted_price
average_fill_price
slippage_bps
all_fees_usd
funding_or_rollover_usd
wallet_and_venue_balance_delta
realized_net_pnl_usd
reconciliation_delay_ms
```

The connector is not accepted until one complete open/close can be explained from request through final balance.
