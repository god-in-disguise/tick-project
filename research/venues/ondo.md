# Ondo Perps

Snapshot: 2026-08-08.

Evidence: documented and public measured; wallet authentication challenge
verified; no signed TICK order yet.

## Bottom Line

Ondo Perps is a serious candidate for TICK's lower-leverage cross-asset route.
It is already live, exposes a documented REST and WebSocket API, and currently
offers 35 enabled markets across crypto, stocks, ETFs, indices, and commodities.

It is not a gTrade replacement for the current high-leverage loop. Current
maximum leverage is 25x, and execution/account truth lives inside Ondo's
offchain SGX exchange rather than in a user-owned onchain position.

A partner agreement is not required for a first canary. A normal wallet can
sign in through SIWE, deposit USDC, and trade through authenticated API calls.
Builder onboarding is useful for sandbox access, higher limits, builder fees,
and a commercial relationship, but it is not the basic trading-auth mechanism.

## Current Live Product

TICK queried the production market and contract endpoints on 2026-08-08:

```text
configured markets: 37
enabled markets:    35

enabled coverage:
  crypto:            2
  stocks:            25
  commodities:       4
  ETFs:              2
  indices:           2

disabled:
  QQQ-USD.P
  SPY-USD.P

production USDC deposit networks exposed by API:
  Ethereum
  Arbitrum
```

Current leverage from the production endpoint:

```text
25x  XAU, XAG, US100, US500
20x  BTC, ETH, AAPL, WTI
15x  BRENT
10x  most stocks and enabled ETFs
 5x  SNDK
```

The public endpoint returned about `$102.8m` in aggregate 24-hour volume and
`$68.1m` in open interest at the time of the snapshot. These are venue-reported
figures, not independently verified volume.

## Execution And Account Model

Orders do not execute as individual public-chain transactions.

```text
wallet signs SIWE challenge
-> account receives JWT or uses an API key
-> TICK submits order through REST
-> offchain SGX exchange engine matches the order
-> private fill/order/position WebSocket publishes account state
```

The exchange engine owns matching, the order book, account balances,
positions, funding, and liquidation. Deposits and withdrawals are onchain.
Each account receives a deposit address, but deposited assets are swept into
an omnibus hot wallet and individual balances are tracked offchain.

For TICK, this means:

- the private fill stream is execution truth;
- the private position stream is exposure truth;
- account balance, funding, and liquidation records are financial truth;
- onchain transfers only prove deposits and withdrawals;
- wallet delta cannot attribute each individual trade;
- there is no callback transaction hash or user-owned onchain position to
  reconcile against.

The normalized venue adapter therefore needs to support both
`onchain_position` and `venue_account_position` ownership models. The UI can
remain venue-agnostic, but audit and reconciliation cannot pretend the models
are identical.

## Self-Service Wallet Path

The production SIWE challenge endpoint accepted the existing TICK service
wallet address without a builder code. The returned challenge used:

```text
domain:   app.ondoperps.xyz
chain ID: 1
auth:     ERC-4361 / SIWE
expiry:   5 minutes after issuance
```

This fits TICK's current platform-created-wallet model: the encrypted per-user
EVM key can sign the SIWE challenge, then the backend can retain the resulting
session. API keys also support scoped permissions and IPv4 allowlisting.

Before external-user use, a canary must prove that an API key can place and
close trades without withdrawal permission. If that scope is unavailable,
TICK must treat the session as a custody credential with withdrawal authority.

## Fees And Small-Ticket Math

The current production market endpoint reports:

```text
maker fee: 1.5 bps per fill
taker fee: 3.5 bps per fill
```

The general fee page currently advertises a limited promotion of 1 bp maker
and 2.5 bps taker. Because these sources disagree, TICK must quote the live
market/account fee returned by the API and must not hardcode the promotion.

At the current public 3.5 bps taker rate:

```text
$10 margin at 10x
notional:             $100
open fee:            $0.035
close fee:           $0.035
round-trip fee:       $0.07  = 0.7% of margin

$10 margin at 20x
notional:             $200
open fee:             $0.07
close fee:            $0.07
round-trip fee:       $0.14  = 1.4% of margin

$10 margin at 25x
notional:             $250
open fee:           $0.0875
close fee:          $0.0875
round-trip fee:      $0.175  = 1.75% of margin
```

Spread, slippage, funding, and optional builder fees remain additional costs.
Builders may add up to 10 bps per fill. TICK should use zero builder surcharge
during the canary.

The production market endpoint exposes base-size increments small enough for
a `$10` ticket on the major markets, but the true minimum accepted order still
needs a signed test.

## Liquidation Economics

Ondo uses cross margin only. Liquidation begins when total margin balance falls
below total maintenance margin. Small positions at or below `$1,000` notional
are liquidated in full.

A liquidation fill can charge `1.5%` of liquidated notional. At maximum
leverage, the theoretical fee relative to initial isolated-equivalent margin
would be:

```text
10x: 15% of margin
20x: 30% of margin
25x: 37.5% of margin
```

The fee is reduced if charging it in full would push the account below
maintenance margin and becomes zero when margin balance is non-positive.
Because the account is cross-margined, TICK cannot present a position-level
"maximum loss" as guaranteed. It must show account margin health and make the
shared-collateral behavior explicit.

## Market Data And Weekend Behavior

Ondo exposes useful public discovery data:

- order-book depth and top of book;
- public trades;
- real OHLCV candles;
- mark and index prices;
- funding rates;
- open interest and reported volume;
- public market schedules and disabled state.

In one Saturday snapshot, top-of-book spreads were approximately:

```text
BTC:    0.15 bps
XAU:    0.32 bps
AAPL:   0.96 bps
US500:  1.11 bps
ETH:    1.56 bps
```

Less liquid markets were materially wider, reaching roughly 6-28 bps. Route
availability must be depth- and spread-aware per market rather than treating
the whole catalog as equally tradeable.

The public mark-price WebSocket produced updates at roughly a two-second
cadence in a short TICK observation. Public trade frequency varied by market;
BTC printed during the sample while XAU and TSLA did not. This is adequate for
venue state and execution overlays, but it is not automatically the best feed
for TICK's live discovery chart.

RWA weekend pricing needs special treatment. When external markets are closed,
Ondo switches from external feeds to internal order-book price discovery. The
internal price is bounded around the last external close by `1 / max_leverage`,
and the mark price is clamped per update. TICK Engine must not interpret this
as ordinary underlying-market volatility or mix it silently with regular-hour
price observations.

## Integration Strengths

- Normal wallet onboarding works without a partner-specific signing scheme.
- Market orders, limit orders, reduce-only, post-only, TP/SL, and TWAP are
  documented.
- Client order IDs provide a natural idempotency key.
- Private order, fill, position, balance, funding, and liquidation streams are
  available.
- API keys use HMAC signing, scoped permissions, and IP allowlists.
- The product has real order-book, trade, OHLCV, funding, and open-interest
  data useful to TICK Engine.
- Deposits and withdrawals do not require users to hold gas for trading;
  Ondo pays withdrawal gas.

## Main Risks

- Position and balance truth are offchain and depend on Ondo's SGX/attestor
  trust model.
- Deposits are swept into an omnibus hot wallet rather than remaining in a
  user-owned position contract.
- Cross margin conflicts with TICK's current one-ticket/one-loss-envelope
  mental model unless each user keeps one isolated venue account and one open
  position.
- The 1.5% notional liquidation fee is material at maximum leverage.
- Public Beta API keys default to one request per second unless Ondo raises the
  account limit.
- Weekend RWA prices are generated from Ondo's internal order book, not a live
  underlying cash market.
- Current docs and live API disagree on headline fee rates and some leverage
  values; runtime market config must be authoritative.
- Jurisdiction restrictions exclude the United States and other prohibited
  regions and must be enforced before account creation and funding.

## Canary Plan

Use a dedicated TICK-owned test wallet, not the operational gas wallet.

```text
1. Complete production SIWE login without builder code.
2. Accept the current terms and create a trading-only API key if supported.
3. Provision an Arbitrum USDC deposit address.
4. Deposit a bounded amount.
5. Open and close one $10 BTC or ETH position at 20x.
6. Open and close one $10 XAU position at 25x.
7. Repeat one RWA test during regular market hours.
8. Withdraw the remaining balance.
```

Record:

```text
request_to_order_ack_ms
ack_to_private_fill_ms
request_to_position_visible_ms
close_request_to_fill_ms
close_fill_to_position_zero_ms
quoted_spread_bps
realized_slippage_bps
maker_taker_fee_usd
funding_usd
venue_balance_delta
deposit_credit_ms
withdrawal_finalization_ms
```

The connector should remain research-only until the normal-wallet cycle,
trading-only credential scope, liquidation event, and withdrawal all reconcile.

## Current TICK Role

Treat Ondo as a high-priority TICK Pro and cross-asset canary. It is especially
interesting for 24/7 access to equities, indices, metals, and oil with a
substantially richer market-data surface than the current oracle venues.

Do not route the main 500x consumer loop to it. The right product fit is a
lower-leverage account mode whose UI and accounting explicitly reflect cross
margin and offchain venue custody.

## Primary Sources

- [Architecture](https://docs.ondoperps.xyz/architecture.md)
- [Builder integration guide](https://docs.ondoperps.xyz/api-reference/integration_guide.md)
- [Production markets endpoint](https://api.ondoperps.xyz/v1/markets)
- [Production contracts endpoint](https://api.ondoperps.xyz/v1/perps/contracts)
- [Markets and leverage](https://docs.ondoperps.xyz/markets.md)
- [Fees](https://docs.ondoperps.xyz/fees.md)
- [Liquidations and insurance](https://docs.ondoperps.xyz/def.md)
- [Weekend and extended-hours trading](https://docs.ondoperps.xyz/weekend-trading.md)
- [API key authentication](https://docs.ondoperps.xyz/api-reference/api_key_authentication.md)
- [Private fill stream](https://docs.ondoperps.xyz/api-reference/private-channels/subscribe:-perps-fills.md)
- [Public Beta limits](https://docs.ondoperps.xyz/public-beta.md)
