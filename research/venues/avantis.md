# Avantis

Snapshot: 2026-08-03.

Evidence: documented; not live tested by TICK.

## Bottom Line

Avantis Zero-Fee Perpetuals is the strongest newly found high-leverage route
for TICK's small-ticket loop. It removes fixed opening and closing trading fees
and charges a variable share only when the trade closes in profit. That can be
materially better than paying a large notional-based fee on a losing $10 trade.

Zero-fee does not mean zero-cost. Dynamic spread, price impact, execution ETH,
and the profit share on a winning close must be measured.

## Current Fit

- Base, USDC collateral, oracle execution.
- ZFP majors include BTC, ETH, SOL, XRP, and HYPE with market-specific maximum
  leverage documented in the 75x-500x range.
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

## Main Risks

- Oracle execution may have the same visible-latency class as gTrade.
- The close requires an ETH execution fee according to the SDK documentation.
- Dynamic spread can dominate a tiny high-leverage trade.
- ZFP behavior differs from Avantis's normal fee market orders; the connector
  must make the order type explicit.
- Stop constraints vary by leverage and must be translated into the preset.

## Canary

1. Query live pair configuration and ZFP eligibility.
2. Quote $10 at 100x, 250x, and the maximum allowed leverage.
3. Open and close one losing trade and one small winning trade.
4. Record profit share, spread, execution fee, callback latency, and wallet
   delta separately.
5. Verify delegated execution and guaranteed stop behavior.

## Primary Sources

- [ZFP fee structure](https://docs.avantisfi.com/trading/zero-fee-perpetuals-zfp/fee-structure-and-comparison)
- [ZFP available assets and features](https://docs.avantisfi.com/trading/zero-fee-perpetuals-zfp/available-assets-features)
- [Guaranteed SL and TP](https://docs.avantisfi.com/trading/guaranteed-sls-tps)
- [Trader SDK operations](https://sdk.avantisfi.com/trade.html)
- [Oracle execution](https://docs.avantisfi.com/trading/accurate-oracle-execution)

