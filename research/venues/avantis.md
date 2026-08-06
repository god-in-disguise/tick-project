# Avantis

Snapshot: 2026-08-03.

Evidence: documented, read-only probed, and live tested by TICK on Base.

## Bottom Line

Avantis Zero-Fee Perpetuals is now a proven high-leverage routing candidate for
TICK's small-ticket loop. Live $10 BTC/USD ZFP trades at 75x and 500x opened
and closed successfully and returned the wallet to a flat state. No fixed
opening or closing trading fee appeared in either losing-trade settlement.

Zero-fee does not mean zero-cost. Dynamic spread, price impact, execution ETH,
and the profit share on a winning close still apply. The 500x canary returned
$8.961121 USDC after a one-second hold and consumed 0.000017815145207003558 ETH
for open and close, including the venue execution fees.

## Current Fit

- Base chain ID 8453, USDC collateral, oracle execution.
- The live pair configuration exposed 115 pairs.
- BTC/USD, ETH/USD, and SOL/USD were ZFP-enabled at probe time with 75x-500x
  leverage. XRP/USD and HYPE/USD were listed but ZFP-disabled, which differs
  from older documentation and confirms that live configuration must be the
  source of truth.
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

Avantis documents a profit-share curve that can fall to 2.5% at high ROI and
says typical users retain more than 80% of profits. TICK must quote the exact
current curve, not a fixed approximation.

The live BTC/USD configuration at the 75x test point showed:

```text
constant ZFP spread:       about 0.0200%
sample price impact:       about 0.0100% per direction
execution fee per action:  about 0.000005615 ETH
```

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

- The clean sample's callback blocks landed two seconds after their respective
  initiation blocks for both open and close.
- The SDK open builder took 2.425 seconds in the research path. This is client
  overhead, not venue execution, and should be precomputed or removed from the
  gesture path.
- HTTP callback polling observed the callback about 3.6-3.9 seconds after the
  initiation receipt. Persistent WSS callback subscriptions are required for a
  production latency comparison.
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

## Measured Latency

The supplied regional Base RPC returned signed transactions quickly. The 500x
cycle measured:

```text
open broadcast response:          210.8 ms
close broadcast response:         197.9 ms
```

The complete 500x research client included avoidable work:

```text
open SDK/feed build:             1,992.5 ms
open receipt to callback poll:   3,866.8 ms
close SDK/feed build:              742.0 ms
close receipt to callback poll:  3,413.6 ms
```

Block timestamps provide the cleaner venue observation:

```text
open initiation -> callback block:   2 seconds
close initiation -> callback block:  2 seconds
```

This is a single clean cycle. It establishes feasibility, not p50 or p95.

## Next Canary

1. Replace HTTP log polling with a pre-armed persistent Base WSS callback
   subscription.
2. Prewarm or cache the SDK inputs so quote construction is outside the hot
   gesture path.
3. Run at least 20 cycles and report callback p50/p95 by block and wall clock.
4. Run comparable 100x and 250x samples, then batch the proven 500x path against
   gTrade's 500x route.
5. Capture a profitable close to verify the exact current profit-share curve.
6. Verify delegated execution and guaranteed stop behavior.

## Evidence

- Read-only probe: `research/experiments/venue-checks/avantis_zfp_probe.py`
- Guarded live canary: `research/experiments/venue-checks/avantis_zfp_canary.py`
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
