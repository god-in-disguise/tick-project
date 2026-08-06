# TICK Venue Rescreen

Snapshot: 2026-08-03.

## Decision

There is no single best venue for TICK. The current evidence supports three
execution lanes:

```text
SMALL-TICKET / HIGH-LEVERAGE
Avantis ZFP, Lighter Standard, Paradex Retail, Aark after partner access

SERIOUS CRYPTO
Hyperliquid, Orderly, Pacifica

CROSS-ASSET
Extended, Orderly, Avantis, Ostium
```

gTrade remains the live route while these candidates are canaried. A second
venue should be enabled because it improves a specific lane, not because it
has a longer market list or a lower headline fee.

## TICK Cost Lens

For collateral `C`, leverage `L`, opening fee rate `f_open`, and closing fee
rate `f_close`:

```text
notional = C * L

explicit round-trip fee in dollars =
  notional * (f_open + f_close)

explicit round-trip fee as a percentage of collateral =
  L * (f_open + f_close) * 100
```

For a symmetric taker fee `f`:

```text
fee drag on collateral = 2 * f * L
```

Examples before spread, slippage, funding, gas, or builder fees:

| Taker fee per fill | Leverage | Round-trip drag on collateral |
| --- | ---: | ---: |
| 0 bps | 50x | 0% |
| 2 bps | 50x | 2.0% |
| 2.5 bps | 50x | 2.5% |
| 3 bps | 100x | 6.0% |
| 4 bps | 50x | 4.0% |
| 4.5 bps | 40x | 3.6% |

This is why the venue hierarchy changes with the preset. Hyperliquid can be a
strong 10x-40x professional route while being economically wrong for a $10,
100x consumer trade. Avantis ZFP can be attractive for the small-ticket loop
even though its profit-share model may be less attractive for a larger winning
trade.

This formula is a screening tool, not a settlement formula. Each connector
must use the venue's current quote and accounting rules for effective
collateral, effective notional, price impact, funding, liquidation, and final
realized PnL.

## Rescreen Matrix

| Venue | Best lane | Current economics | Integration fit | Main unknown |
| --- | --- | --- | --- | --- |
| [Avantis](avantis.md) | Small-ticket high leverage and cross-asset | Receipt-level `$10` matrix measured opening adjustments of `$0.150108` at 75x through `$1.003661` at 500x, with `$0` closing fee in all four losing samples; execution ETH and winning-trade profit share still apply | Live wallet-native 75x/100x/250x/500x canaries passed; optimized local signing, Base Flashblocks, Python SDK, delegated trading, native TP/SL | Keeper callback p50/p95, profitable-close share, delegated lifecycle |
| [Paradex](paradex.md) | Small-ticket crypto | Retail interactive orders are documented as zero fee with a 300 ms speed bump | API subkeys, REST/WS, native TP/SL | Whether TICK's custodial PWA flow qualifies as interactive and its measured fill path |
| [Lighter](lighter.md) | Small-ticket crypto | Standard account has zero maker/taker fees with a 300 ms taker delay | API keys, fast sequencer, broad markets | Signed lifecycle, custody/account model, actual small-order fills |
| [Aark](aark.md) | Small-ticket 500x-1000x | Favorable tested fee model for the loop | Gasless delegated API | TICK needs partner authorization or an accepted origin challenge |
| [Hyperliquid](hyperliquid.md) | Serious crypto | Base taker fee is 4.5 bps before volume discounts | Excellent agent-wallet API and event surface | Effective TICK fee tier and full signed latency |
| [Orderly](orderly.md) | White-label serious crypto | Base taker fee is 3 bps; builders can add fees | Built for brokers/builders, keys, REST/WS, TP/SL | Builder onboarding, account flow, signed p95 latency |
| [Extended](extended.md) | Cross-asset and lower-leverage pro | 2.5 bps taker, zero maker | Broad REST/WS API, external IDs, TP/SL | Stark account UX, effective liquidity and latency by asset |
| [Pacifica](pacifica.md) | Fast crypto fallback | 4 bps taker per fill at the base tier | Agent wallet, client IDs, REST/WS, native TP/SL | Fee drag at 50x and live signed lifecycle |
| [Variational](variational.md) | Future broad cross-asset | Zero explicit trading fee; earns through quoted spread | Attractive RFQ product model | Trading API is not currently public |

## Priority

### 1. Paradex Retail signed canary

It is the strongest newly discovered immediate test. The documented retail
profile combines zero fees, a known 300 ms speed bump, $10 minimum notional,
native trigger orders, API subkeys, and private order/fill streams. The canary
must establish that TICK can legitimately use the interactive profile and that
the 300 ms delay does not hide a larger lifecycle delay.

### 2. Avantis ZFP integration benchmark

The 75x, 100x, 250x, and 500x signed canaries passed. They directly addressed
the problem that hurts gTrade's $10 loop: the 500x opening adjustment measured
about `$1.00`, while all four losing samples reported no closing fee. The
optimized path reduced local encode/sign to single-digit milliseconds and
preconfirmed initiation in roughly 0.36-0.78 seconds. Callback visibility still
took 2.99-4.03 seconds, making Avantis keeper behavior the remaining latency
question. The next benchmark is a 20-cycle p50/p95 batch plus a profitable-close
profit-share sample.

### 3. Lighter Standard signed canary

Lighter remains a clean comparison for zero-fee, speed-bumped CLOB execution.
It should be tested in the same harness as Paradex so that acknowledgement,
fill, visibility, spread, and final balance are directly comparable.

### 4. Hyperliquid and Orderly probes

These are the strongest strategic routes for a serious crypto product. They
should be evaluated at 10x-50x and larger collateral, where liquidity, API
quality, and state truth matter more than extreme leverage.

### 5. Extended cross-asset probe

Extended is the best newly found candidate for replacing slow oracle-style
cross-asset execution with an API/CLOB path. Its public market API currently
exposes hundreds of perpetual products, including crypto, equities,
commodities, indices, and FX with market-specific leverage.

## Screened But Not Prioritized

These venues can be useful products without being the next TICK connector:

| Venue | Why it is behind the shortlist |
| --- | --- |
| Bluefin | Approximately 20x maximum leverage and market-specific minimum sizes weaken the $10 high-leverage loop |
| edgeX | Competitive CLOB infrastructure, but base taker economics and typical leverage do not beat Hyperliquid, Orderly, or Extended for a distinct TICK lane |
| Drift | SWIFT supports fast signed intent delivery, but Solana keeper/fill semantics and best-effort triggers add work without a clear cost or leverage win over Pacifica/Lighter/Paradex |
| GRVT | Good account and API architecture, but the base taker schedule does not improve the small-ticket formula |
| Nado | Low taker fee is interesting, but roughly 20x majors make it a pro-only alternative without enough advantage over the higher-liquidity shortlist |
| Bullet | Low-latency design is interesting, but integration maturity, stable market access, and complete production lifecycle evidence need to improve first |

GMTrade, Ostium, Aster, Aark, Pacifica, Lighter, and Perpl remain documented in
the main venue matrix. They were not forgotten; their current blockers or lane
fit simply did not change in this rescreen.

## Acceptance Rule

A venue is not accepted from documentation or a public endpoint. Each route
must complete a funded open/close and report:

```text
request_to_ack_ms
ack_to_fill_ms
request_to_position_visible_ms
close_request_to_ack_ms
close_ack_to_fill_ms
close_request_to_position_gone_ms
quoted_price
average_fill_price
spread_and_slippage_bps
venue_fees_usd
gas_or_execution_fee_usd
funding_usd
wallet_and_venue_balance_delta
realized_net_pnl_usd
reconciliation_delay_ms
```

The router should ultimately select from normalized primitives:

```text
market available
allowed leverage
minimum collateral and notional
expected all-in round-trip cost
expected acknowledgement and fill latency
native risk controls
account and custody requirements
current route health
user eligibility and balance
```
