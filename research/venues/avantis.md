# Avantis

Snapshot: 2026-08-03.

Evidence: documented, read-only probed, and live tested by TICK on Base.

## Bottom Line

Avantis Zero-Fee Perpetuals is now a proven high-leverage routing candidate for
TICK's small-ticket loop. Live $10 BTC/USD ZFP trades at 75x, 100x, 250x, and
500x opened and closed successfully and returned the wallet to a flat state.
The callback receipts showed no `closingFee` in these losing samples. Their
main deterministic venue cost was the opening execution-price adjustment.

Zero-fee does not mean zero-cost. Dynamic spread, price impact, execution ETH,
and the profit share on a winning close still apply. The 500x canary returned
$8.961121 USDC after a one-second hold and consumed 0.000017815145207003558 ETH
for open and close, including the venue execution fees.

## Current Fit

- Base chain ID 8453, USDC collateral, oracle execution.
- The live pair configuration exposed 115 pairs, with eight currently eligible
  for ZFP execution:

| Market | Pair index | Live leverage range | PnL spread | Minimum notional |
| --- | ---: | ---: | ---: | ---: |
| ETH/USD | 0 | 75x-500x | 0.025% | $100 |
| BTC/USD | 1 | 75x-500x | 0.020% | $100 |
| SOL/USD | 2 | 75x-500x | 0.030% | $100 |
| EUR/USD | 11 | 200x-500x | 0.010% | $300 |
| USD/JPY | 12 | 200x-1000x | 0.010% | $300 |
| GBP/USD | 13 | 200x-500x | 0.010% | $300 |
| XAG/USD | 20 | 75x-250x | 0.300% | $300 |
| XAU/USD | 21 | 75x-250x | 0.020% | $300 |

  XRP/USD and HYPE/USD were listed but ZFP-disabled, which differs from older
  documentation and confirms that live configuration must be the source of
  truth.
- BTC/USD required $100 minimum notional. At 75x this is about $1.33 minimum
  margin, so a $10 ticket is comfortably valid.
- ZFP currently uses market orders and supports adding collateral.
- Guaranteed stop-loss and take-profit orders are venue-native.
- Python SDK builds opens, closes, collateral updates, and TP/SL updates.
- SDK exposes `MARKET_ZERO_FEE` as an order type.
- Delegation methods are documented by the SDK.

## TICK Economics

The useful comparison is asymmetric:

```text
losing close:
  fixed venue trading fee = 0
  remaining costs = spread + price impact + execution + funding-like costs

winning close:
  remaining costs + variable share of gross profit
```

The live PairStorage configuration and `getPnlBasedFee` view agree on the
current profit-share tiers. The percentage applies to gross profit, not
collateral:

| Collateral ROI | Profit share |
| ---: | ---: |
| below 1% | 80% |
| 1% to below 5% | 50% |
| 5% to below 25% | 45% |
| 25% to below 50% | 37.5% |
| 50% to below 100% | 27.5% |
| 100% to below 500% | 25% |
| 500% to below 1500% | 22.5% |
| 1500% to below 2500% | 15% |
| 2500% and above | 2.5% |

TICK reads this curve from the live venue catalog and includes it in winning
live-PnL estimates. Losing PnL is not charged this profit share.

The live BTC/USD configuration showed:

```text
constant ZFP spread:       about 0.0200%
receipt execution adjustment: about 0.0200% of notional on open
receipt execution adjustment: $0 on close in all four optimized samples
receipt closingFee:        $0 in all four optimized samples
execution fee per action:  about 0.000005615 ETH
```

The receipt-level matrix isolated price-oracle movement from venue adjustment:

| Leverage | Notional | Opening adjustment | Adjustment as margin | Closing fee |
| ---: | ---: | ---: | ---: | ---: |
| 75x | $750 | $0.150108 | 1.50% | $0 |
| 100x | $1,000 | $0.200176 | 2.00% | $0 |
| 250x | $2,500 | $0.501099 | 5.01% | $0 |
| 500x | $5,000 | $1.003661 | 10.04% | $0 |

### Verified 500x liquidation canary

On 2026-08-06, TICK opened a `$10` ETH/USD ZFP long at 500x through the
platform-funded delegated path. The position was confirmed by Avantis's
`MarketExecuted` callback at an open price of `1905.7910367416`. It was later
liquidated by a venue-native `LimitExecuted` event with `orderType = 2` at
`1902.51`.

```text
Adverse price move:
  (1902.51 - 1905.7910367416) / 1905.7910367416
  = -0.172161%
  = -17.216 bps

Approximate 500x gross margin effect:
  -0.172161% × 500
  = -86.0806% of collateral

Approximate collateral remaining before venue liquidation:
  100% - 86.0806%
  = 13.9194%

Observed returned collateral: $0
Observed terminal reason: liquidation
```

The liquidation transaction was
`0xc5444c162f3cc9d48afce5a35ef31725032ddc904a1006edbbb92cc95e8d051e` at
Base block `49614190`. The loss was not caused by a missing open or a failed
close. The position remained on-chain open until the liquidation event.

This incident also exposed an integration issue: the Avantis API briefly
reported no trade while on-chain `openTradesCount` was still `1`. Close
preflight now checks on-chain storage first and uses the API only as a
fallback. Terminal monitoring must still backfill callback logs after every
stream gap so a liquidation is shown immediately rather than remaining
`unknown`.

This is materially better for TICK's `$10` high-leverage loop than the current
gTrade 500x estimate of roughly `$2.50` in round-trip venue cost. It is still
not a guaranteed quote: market movement during oracle execution, dynamic
impact, ETH execution cost, funding-like adjustments, and profitable-close
profit share can change the wallet result.

The clean one-second-hold canaries settled:

```text
75x margin:                 $10.000000
75x returned collateral:    $9.792732
75x USDC result:            -$0.207268
75x ETH consumed:           0.00001814855418080276

500x margin:                $10.000000
500x returned collateral:   $8.961121
500x USDC result:           -$1.038879
500x ETH consumed:          0.000017815145207003558

final venue state:          flat after both cycles
```

These are individual losing samples, not stable fee estimates. The price path
during the oracle windows can offset or amplify spread and impact, so a sample
batch is still required before route-selection thresholds are set.

## Main Risks

- The optimized callbacks were visible 2.99-4.03 seconds after their gestures.
  Callback execution sometimes landed in the next sealed Base block and
  sometimes skipped one, so a next-block assumption is not valid.
- Base Flashblocks exposes callbacks before block seal. TICK can use this as a
  clearly labeled preconfirmed state, while financial settlement and final
  state must wait for sealed callback and position reconciliation.
- Open and close each require an ETH execution fee.
- Dynamic spread can dominate a tiny high-leverage trade.
- ZFP behavior differs from Avantis's normal fee market orders; the connector
  must make the order type explicit.
- Stop constraints vary by leverage and must be translated into the preset.
- Live pair eligibility can diverge from older documentation.
- The callback trade field `initialPosToken` is the collateral amount used for
  a full close. Passing `positionSizeUSDC` as the close amount reverts with
  `INV_AMOUNT`.
- A 500x attempt exposed a stale nonce in the SDK-built transaction after an
  approval. The canary now replaces every template nonce with the wallet's
  pending nonce immediately before gas estimation and signing. The rejected
  transaction never reached Avantis; the corrected cycle used nonces 8 and 9.

## Local Connector Status

The production-shaped local backend now has an isolated `avantis` venue mode.
It uses the same user identity and encrypted wallet key as TICK, but derives
balance, market state, execution, history, PnL, and gas accounting from Base.
Switching venue is blocked while any position or command is active.

The connector currently provides:

- live ZFP catalog and Pyth Lazer prices through the official SDK;
- Base user-wallet USDC balance and venue-specific gas accounting;
- automatic platform-funded setup ETH, USDC approval, and Avantis delegation;
- delegated market open and full close;
- deterministic transaction hash persistence before broadcast;
- pre-armed Base callback listening with `pendingLogs` when available;
- `MarketExecuted` open/manual-close handling;
- `LimitExecuted` take-profit, stop-loss, and liquidation handling;
- recent-log replay after process restart;
- wallet reconciliation after terminal events.

This mode is intentionally local-only until the configured Base service wallet
is funded and a complete open, close, restart-recovery, and terminal-event
canary passes. It has not replaced the production gTrade route.

## Measured Latency

The optimized client moved all SDK, price-feed, execution-fee, fee-envelope,
nonce, and gas work outside the gesture path. It then used local calldata
encoding and signing, a reused QuickNode HTTP connection, and a pre-armed Base
Flashblocks `pendingLogs` subscription.

Four `$10` BTC/USD samples measured:

| Leverage | Open preconfirm | Open visible | Close preconfirm | Close visible |
| ---: | ---: | ---: | ---: | ---: |
| 75x | 357.9 ms | 3.444 s | 778.4 ms | 4.017 s |
| 100x | 490.2 ms | 3.242 s | 363.1 ms | 2.993 s |
| 250x | 501.2 ms | 3.223 s | 757.9 ms | 4.027 s |
| 500x | 363.4 ms | 3.465 s | 765.0 ms | 4.029 s |

Cross-sample medians:

```text
open encode + sign:              8.6 ms
open RPC response:             197.6 ms
open initiation preconfirmed:  426.8 ms
open callback visible:           3.343 s

close encode + sign:             7.9 ms
close RPC response:            193.2 ms
close initiation preconfirmed: 761.5 ms
close callback visible:          4.022 s
callback visible -> sealed:      1.175 s
```

Receipt decoding isolates the second leg more precisely. Every live callback
used `executeMarketOrders`, Pyth Lazer, and a signed price update embedded in
the keeper transaction. The signed payload includes the oracle timestamp at
microsecond precision.

| Leverage | Leg | Initiation preconfirm -> oracle sample | Oracle sample -> callback observed | Gesture -> callback observed |
| ---: | --- | ---: | ---: | ---: |
| 75x | open | 2,433.5 ms | 653.0 ms | 3,444.4 ms |
| 75x | close | 2,567.4 ms | 671.1 ms | 4,016.9 ms |
| 100x | open | 2,084.0 ms | 667.6 ms | 3,241.8 ms |
| 100x | close | 1,968.1 ms | 661.3 ms | 2,992.5 ms |
| 250x | open | 2,075.7 ms | 646.1 ms | 3,222.9 ms |
| 250x | close | 2,594.7 ms | 674.8 ms | 4,027.5 ms |
| 500x | open | 2,467.6 ms | 634.3 ms | 3,465.3 ms |
| 500x | close | 2,600.3 ms | 663.9 ms | 4,029.2 ms |

The oracle-to-callback interval is tightly grouped at 634-675 ms. The larger
and more variable delay is before Avantis samples the signed oracle update.
For the 500x open, for example:

```text
gesture:                         19:32:15.968971 UTC
initiation preconfirmed:         19:32:16.332393 UTC
Pyth Lazer source price sampled: 19:32:18.800000 UTC
MarketExecuted pending log:      19:32:19.434283 UTC
```

The source price therefore existed 634 ms before TICK observed execution, but
the trade was not economically open at the source timestamp. The position is
created atomically when the keeper callback executes and emits
`MarketExecuted`. TICK already consumes that event through Base Flashblocks
`pendingLogs`, around 1.17 seconds before the callback block seals. There is no
material REST, indexer, or frontend delay hidden after the real execution.

A separate warm-connection probe of Avantis's public signed-price endpoint
took 1.15-1.62 seconds per response. This is not a direct trace of the private
keeper, but it supports the conclusion that on-demand signed-price production
is a meaningful part of the pre-oracle interval.

The client hot path is no longer the material bottleneck. The remaining delay
is predominantly the Avantis keeper and signed-price reaction after initiation
is already preconfirmed. Four samples establish an initial matrix, not p95.

## Can TICK Execute the Callback Faster?

Not without Avantis cooperation. `executeMarketOrders` is protected by
`onlyOperator`, and operator access is changed by protocol governance. TICK can
fetch the same public signed Pyth Lazer update, but an ordinary TICK wallet
cannot submit the economic callback.

There are two realistic protocol-level improvements:

1. Avantis keepers consume Base Flashblocks preconfirmed initiation events and
   start the signed-price request before block seal.
2. Avantis authorizes a TICK-operated keeper, allowing TICK to observe the
   initiation, fetch a fresh signed update, and submit the callback directly.

The second option needs production-grade keeper redundancy, fee management,
monitoring, and strict order validation. Until either option exists, TICK can
optimize initiation and detection but cannot safely manufacture an earlier
filled state.

## Next Canary

1. Run at least 20 optimized cycles and report callback p50/p95 by block and
   wall clock.
2. Ask Avantis whether its keeper consumes Flashblocks/preconfirmed initiation
   events or waits for sealed state, and whether TICK can run an authorized
   operator. This is now the largest latency question.
3. Batch the proven 500x path against gTrade's 500x route.
4. Capture a profitable close to verify the exact current profit-share curve.
5. Fund the Base service wallet and complete a local delegated canary through
   the TICK API and worker, including automatic account setup.
6. Verify a venue-native guaranteed stop through the local terminal reducer.

## Evidence

- Read-only probe: `research/experiments/venue-checks/avantis_zfp_probe.py`
- Guarded live canary: `research/experiments/venue-checks/avantis_zfp_canary.py`
- Optimized live canary:
  `research/experiments/venue-checks/avantis_zfp_optimized_canary.py`
- Receipt decoder:
  `research/experiments/venue-checks/avantis_zfp_receipt_analysis.py`
- Optimized latency/cost matrix:
  `research/experiments/venue-checks/reports/avantis/optimized_matrix.md`
- Clean live report:
  `research/experiments/venue-checks/reports/avantis/latest_live.json`
- Clean 500x live report:
  `research/experiments/venue-checks/reports/avantis/latest_500x_live.json`

## Primary Sources

- [ZFP fee structure](https://docs.avantisfi.com/trading/zero-fee-perpetuals-zfp/fee-structure-and-comparison)
- [ZFP available assets and features](https://docs.avantisfi.com/trading/zero-fee-perpetuals-zfp/available-assets-features)
- [Guaranteed SL and TP](https://docs.avantisfi.com/trading/guaranteed-sls-tps)
- [Trader SDK operations](https://sdk.avantisfi.com/trade.html)
- [Oracle execution](https://docs.avantisfi.com/trading/accurate-oracle-execution)
- [Trading implementation](https://basescan.org/address/0x821c380cce2eeeb07778757a52c1219fae5761a9#code)
- [Price aggregator implementation](https://basescan.org/address/0x4efea74ffd48cfa37dd7282df0ee4b22f08e74f9#code)
- [Pyth Lazer verifier implementation](https://basescan.org/address/0xbe065fb09d9893e3d8df10ad7e73ee153a438a64#code)
- [Base Flashblocks overview](https://docs.base.org/base-chain/api-reference/flashblocks-api/flashblocks-api-overview)
- [Base pendingLogs](https://docs.base.org/base-chain/api-reference/flashblocks-api/pendingLogs)
