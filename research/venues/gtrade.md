# gTrade / Gains

Snapshot: 2026-07-26.

Status: live tested with TICK founder/demo wallet on Arbitrum.

## Bottom Line

gTrade is the selected first live MVP route. It fits the TICK loop because it supports high leverage, USDC collateral on Arbitrum, wallet-owned positions, delegated execution, broad market coverage, and real venue-native stops.

The main risk is still state correctness rather than basic order placement. gTrade market opens and closes require oracle fulfillment, so the backend must distinguish initiation transaction confirmation from actual venue execution/callback. The local canary proved the loop is usable, but production must harden quote truth, native stops, direct events, PnL, and reconciliation.

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

The local test wallet progressed beyond dry calls. TICK opened and closed real BTCDEGEN/USD 500x and BTC/USD 100x positions, tested delegated execution, tested venue stops, observed real fee drag, and measured the difference between initiation confirmation, venue callback, UI state, and final wallet delta.

Representative lessons:

```text
$10 ticket at 500x degen pair
requested notional: about $5,000
round-trip venue fee drag: about $1.85-$2.00 before meaningful market movement
position visibility: usable, but not instant
close visibility: improved after cache-first close, but still needs direct event/reducer hardening
```

The exact numbers vary by sample, market, route, RPC, and oracle callback timing. Do not use one canary as a production SLA.

July 28 production-backend extraction sample:

```text
$15 BTC/USD long, 100x, $2 venue stop
API acceptance:                   23.7 ms
local wallet preparation:          2.0 ms
write RPC response:             1,099.1 ms
receipt observed:               1,561.7 ms
direct open callback:           2,110.4 ms
position visible to canary:     2,277.4 ms
close visible to canary:        2,673.2 ms
final wallet result:              -$1.305076
```

The first platform-agent implementation regressed visible open to `3.35s`.
Removing a redundant balance RPC and quote-preparation lock contention returned
the path to `2.28s`, effectively the same as the previous direct-signing
baseline (`2.26s`). This restored the old speed; it did not make the venue
faster. In the corrected trace, local preparation was no longer material.

The next transport audit found one remaining local warm-up regression: the
primary RPC was kept active by fee refreshes, but the direct-sequencer provider
was lazy and could lose its TLS connection between trades. Cold TLS measured
`0.58-0.85s`; connection reuse measured about `0.19s`. The worker now primes
the direct sequencer at startup and keeps that session active every ten
seconds.

## Execution Model

- TICK creates one Arbitrum wallet per user and encrypts its key in Postgres for the private MVP.
- The user wallet owns collateral, positions, and PnL.
- One-time setup approves the diamond and delegates trading to TICK's execution agent.
- The agent submits normal opens/closes and pays ETH gas; actual gas is charged to the user's USDC ledger.
- Setup and withdrawals still use the user-wallet signer.
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

- Open/close latency is acceptable for canary/product validation, but needs p50/p95 measurement after production extraction.
- Oracle fulfillment means sub-second guaranteed execution is not a safe assumption.
- Degen pairs are high leverage but may have different fees, spread, and risk mechanics.
- Forex/commodities/stocks have market-hour and gap behavior.
- Delegated trading is powerful; TICK policy must prevent reckless or unintended execution.
- Current docs and live values differ in places, so connector must rely on live backend variables.
- Silent leverage normalization is not acceptable: displayed leverage/exposure must match submitted leverage/exposure.
- Phone-side PnL formulas are not authoritative; backend must publish estimated net PnL and final realized result.

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

## Next Work

1. Extract gTrade into `builds/tick-mvp/` as primitives: quote/config, transaction building, submission, exact event decoding, snapshots, and reconciliation.
2. Enforce direction-specific visible preflight: displayed terms must equal submitted terms.
3. Require venue-native stop for real-money opening.
4. Persist deterministic transaction hash and nonce before broadcast.
5. Use direct callback/on-chain logs as normal execution truth, with Gains WS and REST as supplemental/recovery sources.
6. Keep wallet delta as aggregate canary truth while storing venue-derived fee/PnL fields.
7. Run 30-50 clean open/close cycles before enabling another live route.

## Primary Sources

- [Overview](https://docs.gains.trade/gtrade-leveraged-trading/overview)
- [Trading contracts](https://docs.gains.trade/developer/integrators/trading-contracts)
- [Delegated trading](https://docs.gains.trade/developer/integrators/delegated-trading)
- [Backend](https://docs.gains.trade/developer/integrators/backend)
- [Live prices and OHLC snapshots](https://docs.gains.trade/developer/integrators/price-feed)
- [Arbitrum contract addresses](https://docs.gains.trade/what-is-gains-network/contract-addresses/arbitrum-mainnet)
