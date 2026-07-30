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

Snapshot: 2026-07-30.

| Venue | Evidence | Best TICK use | Execution model | Useful leverage | Baseline trading cost | Rewards | Current view |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [Aark](aark.md) | Live tested | Small-ticket high-leverage crypto | Gasless API/relayer with per-user delegated signer and venue balance | BTC 500x/750x/1000x in current live config | 1 bp open fee plus $0.60 execution fee in the live canary; losing close charged no trading fee | Existing AARK/VIP programs; not a routing reason | Full round trip works with Aark-origin challenge and live EIP-712 signing; TICK-origin challenges and documented EIP-191 opens are currently rejected |
| [GMTrade](gmtrade.md) | Live tested | High-leverage crypto and cross-asset feed | Solana order transaction followed by keeper/oracle execution; pool based | Live BTC 500x, ETH ~294x, SOL 250x; 54 markets at 100x+ | Crypto/stock/commodity: 1.0-1.2 bps per fill | GT points explicitly qualify users for its TGE | Public keeper path too slow; viable only with private/order-keeper lane |
| [Perpl](perpl.md) | Documented | Farming/upside research venue | Fully on-chain CLOB perps on Monad | Unknown from current docs | Unknown from current docs | Likely early-stage upside; exact points/builder program needs confirmation | Likely what partner meant by "Purple"; worth contacting, not accepted as execution rail yet |
| [Pacifica](pacifica.md) | Public measured | Fast crypto execution | Hybrid off-chain CLOB on Solana; signed REST/WS | BTC/ETH 50x, SOL 20x | Tier-1 taker 4 bps per fill | 10M points weekly; builder program | Best next live crypto test |
| [Lighter](lighter.md) | Documented + public measured | Fast prototype route | Off-chain sequencer with ZK settlement on Ethereum | BTC/ETH 50x, SOL 25x; selected RWAs/indices 20-50x | Standard account: zero maker/taker, 300 ms taker delay | Season 2 points, but not the core reason to use it | Strongest next investor-demo candidate if API-key model is acceptable |
| [Aster](aster.md) | Documented + public measured | Higher leverage, liquidity, points | Aster Perpetuals V3 API-agent path; separate 1001x direct-contract path on BNB/Arbitrum | Perps market-specific; Arbitrum 1001x config returned 500BTC at 1000x, BTC/ETH at 250x | Perps docs show 4 bps taker; 1001x live config returned $0.20-$0.50 execution fee and zero open fee on tested high-leverage pairs | Stage 6 points; Aster Code builder fees | V3 is usable API route; 1001x wallet route is currently reduce-only, so opens are blocked |
| [gTrade / Gains](gtrade.md) | Live tested | First live MVP route | Arbitrum direct contract or delegated trading, oracle fulfillment | Forex 1000x, degen crypto 500x, BTC/ETH 200x, commodities 250x | Pair-specific; live backend exposes fee groups and minimum notional | Credits/revenue programs exist, but not core for TICK | Selected first rail; harden execution, PnL, stops, events, and reconciliation before adding second live venue |
| [Ostium](ostium.md) | Live tested | Stocks, indices, commodities, FX | Arbitrum transaction plus oracle callback | Pair-specific, up to 200x | 3-10 bps open plus oracle and possible early-close cost | Points/rewards need current verification | Keep for cross-asset; weak first crypto rail |

Costs above are venue schedules, not all-in TICK costs. Spread, slippage, funding or rollover, builder fees, gas, reserves, and liquidation mechanics still apply.

## Current Test Order

1. Harden the gTrade live route inside `builds/tick-mvp/`: quote truth, native stop, direct events, reducer, reconciliation, and deterministic transaction recovery.
2. Send Aark the measured compatibility matrix: TICK-origin challenge returns `9999`, documented EIP-191 returns `Invalid Signature`, and Aark-origin EIP-712 succeeds. Ask them to authorize TICK's origins or register a partner address, confirm EIP-712 as canonical, and provide the staging site key.
3. Keep the current private/provider Arbitrum RPC as default write path until a benchmark beats it by p95; direct sequencer remains a measured fallback candidate.
4. Ask Kairos whether public intake is allowlisted or requires an integrator setup before spending more time on Timeboost.
5. Lighter signed latency/cost probe if API-key execution remains acceptable.
6. Ask Aster whether the tested 1001x BNB/Arbitrum contracts are the active production trading path, and why direct opens revert as temporarily unavailable.
7. Pacifica only if 50x leverage is acceptable for a specific fallback route.
8. Keep Ostium as the live-tested wallet-native cross-asset connector and accounting benchmark.

This is a research order, not a final routing decision. Production routing should be chosen from measured fill latency, all-in cost, state consistency, market coverage, user eligibility, and operational control. Points are secondary.

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
