# gTrade / Gains

Snapshot: 2026-07-20.

Status: official documentation and public Arbitrum backend measured; no TICK signed trade yet.

## Bottom Line

gTrade is the best next high-leverage venue to test after GMTrade. It fits the wallet-native thesis better than Lighter because users keep custody and do not need an exchange deposit account. It also has a documented delegated trading primitive that could support one-click execution after user approval.

The main risk is latency. gTrade market opens and closes require oracle fulfillment, so it may feel closer to Ostium/GMTrade than Lighter unless the request-to-execution path is fast enough in practice.

## Live Arbitrum Snapshot

Public backend checked on 2026-07-20:

```text
Backend: https://backend-arbitrum.gains.trade
Trading state: 0
Pairs returned: 482
Block confirmations: 1
Collateral tokens: DAI, WETH, USDC, GNS
Diamond: 0xFF162c694eAA571f685030649814282eA457f169
```

Highest leverage groups from the live payload:

```text
Forex majors:      1000x
Forex minors:       750x
Crypto degen:       500x
Commodities tier 1: 250x
Normal BTC/ETH:     200x
Altcoins:           150x
Stocks:              50x
```

Selected high-leverage live pairs:

```text
EUR/USD        1000x
USD/JPY        1000x
GBP/USD        1000x
USD/CAD        1000x
BTCDEGEN/USD    500x
ETHDEGEN/USD    500x
SOLDEGEN/USD    500x
BNBDEGEN/USD    500x
HYPEDEGEN/USD   500x
ZECDEGEN/USD    500x
XAU/USD         250x
BTC/USD         200x
ETH/USD         200x
```

The 500x degen crypto group has a minimum notional of about $5,000, so at 500x the minimum collateral is about $10. Normal BTC/ETH at 200x have a minimum notional of about $2,857, so the minimum collateral is about $14.29.

The local test wallet on 2026-07-20 had enough USDC for a small canary but had zero USDC allowance to the Gains diamond. A dry `openTrade` gas estimate using the current v10 trade struct reached the contract and reverted with the expected ERC-20 allowance error. This means the current calldata shape is usable; approval is the next blocker before a live open.

## Execution Model

- User connects an EVM wallet.
- User keeps custody of collateral.
- For direct trading, the user approves the diamond contract to spend collateral and signs trade transactions.
- For delegated trading, the user sets a trading delegate.
- The delegate can submit trading actions for the trader, while collateral and PnL remain tied to the trader.
- Opens/closes emit request events first, then oracle fulfillment events.

This fits TICK better than a fully custodial backend. The delegated path is useful, but it is broad authority and must be constrained by backend policy, per-user limits, allowed pairs, notional caps, and revocation UX.

## TICK Fit

Strengths:

- Very high leverage on the exact kind of products TICK wants.
- Wallet-native flow, no normal exchange account required.
- USDC collateral on Arbitrum is supported.
- Broad market variety: crypto, degen crypto, forex, commodities, stocks, indices.
- Pricing websocket updates are fast enough for the feed layer.
- Delegated trading can support a faster UX than asking the user to sign every open/close.

Risks:

- Real open/close latency is still unknown.
- Oracle fulfillment may make it too slow for a 30-60 second loop.
- Degen pairs are high leverage but may have different fees, spread, and risk mechanics.
- Forex/commodities/stocks have market-hour and gap behavior.
- Delegated trading is powerful; TICK policy must prevent reckless or unintended execution.
- Current docs and live values differ in places, so connector must rely on live backend variables.

## Probe

Read-only public probe:

```bash
venue-checks/.venv/bin/python venue-checks/gtrade_public_probe.py --stream-seconds 3 --wallet
```

Dry-estimate an open without broadcasting:

```bash
venue-checks/.venv/bin/python venue-checks/gtrade_public_probe.py \
  --stream-seconds 0 \
  --wallet \
  --dry-open BTCDEGEN/USD \
  --dry-open-margin 10 \
  --dry-open-side long
```

The probe prints:

```text
trading state
pair count
top leverage pairs
selected TICK watchlist prices
price websocket update rate
optional wallet balances and allowances
```

## Next Test

1. Use Arbitrum USDC collateral.
2. Test direct `openTrade` with a small BTCDEGEN/USD or BTC/USD position.
3. Measure request transaction confirmation, oracle fulfillment, position visible delay, close request, close fulfillment, final balance delta.
4. If direct signing is too much friction, test delegated trading with a dedicated agent wallet.
5. Compare against GMTrade and Ostium using the same `$10-$20 margin, 3-5 second hold` canary.

## Primary Sources

- [Overview](https://docs.gains.trade/gtrade-leveraged-trading/overview)
- [Trading contracts](https://docs.gains.trade/developer/integrators/trading-contracts)
- [Delegated trading](https://docs.gains.trade/developer/integrators/delegated-trading)
- [Backend](https://docs.gains.trade/developer/integrators/backend)
- [Live prices and OHLC snapshots](https://docs.gains.trade/developer/integrators/price-feed)
- [Arbitrum contract addresses](https://docs.gains.trade/what-is-gains-network/contract-addresses/arbitrum-mainnet)
