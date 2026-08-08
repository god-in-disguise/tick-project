# Decibel

Snapshot: 2026-08-08.

Evidence: documented and public-page measured; production REST authentication
verified; no signed TICK order yet.

## Bottom Line

Decibel is a high-priority candidate for TICK's fast lower-leverage and
cross-asset route. It is a fully onchain central-limit order book on Aptos:
orders, matching, fills, positions, margin, and liquidation all settle onchain.
That gives TICK a cleaner execution-truth model than an offchain account venue
and removes the separate oracle callback used by gTrade and Avantis.

It is not a replacement for TICK's 500x route. The public BTC product currently
offers 40x, while SPY is the highest documented current market at 50x. Decibel
is more interesting as a fast serious-trading route across crypto, equities,
ETFs, commodities, and indices.

A partner agreement is not required to build the first technical canary.
Credentials and a gas station can be created through Geomi, API wallets are
self-service, and the TypeScript SDK is public. A commercial and terms review
is still required before TICK exposes automated customer trading: Decibel's
public developer documentation encourages API trading, while the current terms
contain broad restrictions on automated access and commercial exploitation.

## Current Product And Markets

Decibel mainnet launched on Aptos in February 2026. The public BTC trading page
currently exposes:

```text
market:                  BTC/USD
maximum leverage:        40x
margin mode:             cross
order types:             market, limit, stop
position controls:       reduce-only, TP, SL
headline taker fee:      0.0340%
headline maker fee:      0.0110%
```

Current announcements document a broad catalog with market-specific leverage:

```text
50x  SPY
40x  BTC
30x  QQQ
25x  ETH, GOLD, SILVER
20x  SOL, XRP, WTIOIL, AAPL, MSFT, META, NVDA, GOOGL, AMZN, EWY
10x  HYPE, BNB, DOGE, MSTR, TSLA, COIN, HOOD, AMD, INTC,
     SAMSUNG, NATGAS, COPPER
 5x  CRCL, SPCX, LIT and selected smaller markets
```

Announcements are not an authoritative runtime market snapshot. Parameters can
change and markets can be blocked. TICK's production API request to the current
mainnet markets endpoint returned `401 Unauthorized` without a Geomi bearer
token, so the exact enabled-market list, minimum sizes, depth, and live risk
parameters still need to be captured after credential setup.

The public BTC page reported roughly `$16.4m` 24-hour volume and `$2.25m` open
interest during the snapshot. These are venue-reported dynamic figures, not an
independent liquidity measurement.

## Execution And Truth Model

The documented lifecycle is:

```text
TICK builds an Aptos transaction
-> user's API wallet signs it
-> TICK or Geomi Gas Station submits it
-> Decibel's onchain CLOB checks margin and matches the order
-> Aptos commits the transaction and fill events
-> private WebSocket publishes order, fill, position, and account updates
```

`placeOrder()` returning a transaction hash proves submission, not a fill. The
official starter kit explicitly describes the hash as a ticket to the queue and
requires WebSocket or onchain observation for the final result.

For TICK, the source hierarchy should be:

```text
order accepted:       deterministic Aptos transaction hash
order filled:         committed onchain fill event / transaction version
fast position state:  private position and user-trade WebSocket streams
account state:        onchain Trading Account plus account WebSocket
recovery:             REST snapshot and direct Aptos transaction/events
financial result:     user-trade fee, funding, realized PnL, account delta
```

WebSocket streams include:

- order updates;
- user fills with fee, realized PnL, and realized funding fields;
- open positions and account overview;
- liquidation notifications;
- prices, trades, depth, open interest, funding, and OHLCV.

The WebSocket requires bearer-token authentication, closes sessions after one
hour, sends ping frames every 30 seconds, and expects clients to reconnect,
restore subscriptions, and use sequence numbers to identify gaps. TICK must
backfill account and order state after every reconnect rather than relying on
the live stream alone.

## Account And Key Model

Decibel separates three account roles:

```text
Login Wallet
  creates and manages access

API Wallet
  delegated Aptos key that signs programmatic trading transactions

Trading Account / subaccount
  onchain object holding USDC collateral, positions, and margin state
```

The public API page and CLI documentation state that API wallets can trade
without deposit or withdrawal authority. This fits TICK's security model well:
one per-user Aptos Trading Account, one encrypted trade-only API wallet, and a
separate path for collateral withdrawals.

This adds a chain-specific account layer but does not require venue-specific
product semantics. The normalized primitive is:

```text
VenueAccount
  venue
  chain
  owner identity
  collateral account
  trading credential
  withdrawal authority
  gas policy
  lifecycle status
```

TICK should never model the Decibel API Wallet as the user's deposit address.
The collateral owner and the trade signer are deliberately separate roles.

## Gas Sponsorship

Every write is an Aptos transaction and normally requires APT. Geomi Gas
Station supports sponsored transactions directly through the Decibel SDK:

```text
user/API wallet signs the transaction as sender
-> Geomi signs as fee payer
-> gas is charged to TICK's gas-station account
-> the trade signer never needs APT
```

Gas-station creation is self-service and supports allowlists, per-wallet limits,
global limits, and CAPTCHA. This is a strong match for TICK's USDC-only user
experience. TICK can either absorb sponsored gas or record the exact Aptos gas
cost and recover it through its normal USDC gas ledger.

The current official SDK package is `@decibeltrade/sdk` version `0.7.0` at the
time of this snapshot. TICK should pin the exact package version and deployed
package address in any connector.

## Fees And Small-Ticket Math

Tier 0 fees are:

```text
taker: 3.4 bps per fill
maker: 1.1 bps per fill
```

For an immediate market open and market close:

```text
round-trip fee as percent of margin
  = 2 * leverage * 0.034%

10x:  0.68% of margin
20x:  1.36% of margin
25x:  1.70% of margin
30x:  2.04% of margin
40x:  2.72% of margin
50x:  3.40% of margin
```

Examples:

```text
$10 margin at 40x BTC
notional:             $400
open taker fee:      $0.136
close taker fee:     $0.136
round-trip fee:      $0.272 = 2.72% of margin

$10 margin at 50x SPY
notional:             $500
open taker fee:       $0.17
close taker fee:      $0.17
round-trip fee:       $0.34 = 3.40% of margin
```

Spread, realized slippage, continuous funding, Aptos gas, and an optional
builder fee are additional. Maker orders reduce the explicit fee but are not a
replacement for immediate execution in TICK's main gesture loop.

Builder fees are optional and added to the user's trading fee. A user must
first approve the maximum fee for a builder address. TICK should use no builder
surcharge during the canary and decide commercial pricing separately after
all-in execution economics are measured.

## Liquidation Economics

Decibel is cross margin only. Account equity includes collateral, unrealized
PnL, and accrued funding. Liquidation eligibility is:

```text
account equity < total maintenance margin

maintenance margin fraction
  = 1 / (maximum market leverage * 2)
```

For a single position in an otherwise empty dedicated Trading Account, this
implies approximately:

```text
40x market
initial margin:       2.50% of notional
maintenance margin:  1.25% of notional
price loss to MM:     about 1.25%
margin consumed:      about 50%

50x market
initial margin:       2.00% of notional
maintenance margin:  1.00% of notional
price loss to MM:     about 1.00%
margin consumed:      about 50%
```

This approximation excludes fees, funding, spread, slippage, and the effect of
other collateral or positions. In a shared cross-margin account, the position
can consume more of the account before liquidation, so a position-level maximum
loss is not guaranteed.

Liquidation has two stages:

1. A bounded market order tries to close enough exposure and leaves remaining
   collateral in the account.
2. If equity falls below two-thirds of maintenance margin, the Backstop
   Liquidator takes over the account and crystallizes positions at mark.

The public liquidation page does not specify a fixed liquidation penalty.
TICK must capture the actual liquidation event and account delta in a bounded
canary before making claims about returned collateral. Auto-deleveraging is a
separate final circuit breaker that can close profitable opposing positions at
the bankruptcy price during an extreme backstop deficit.

## Product Strengths

- Fully onchain order placement, matching, fills, positions, and liquidation.
- No second oracle-callback transaction after the user order.
- Market, limit, post-only, IOC, reduce-only, stop, native TP/SL, TWAP, and
  client order IDs are documented.
- Dedicated API wallets support programmatic trading without withdrawal
  authority.
- Gas sponsorship removes the APT requirement from the user experience.
- Private streams expose fill fees, realized PnL, funding, position state, and
  liquidation notifications.
- Cross-chain USDC onboarding supports Ethereum, Arbitrum, Base, and Solana
  users through the venue interface.
- Broad 24/7 catalog includes crypto, equities, ETFs, indices, and commodities.
- Builder codes provide an optional revenue path with explicit user approval.
- OtterSec reports are published for perps, liquidations/vaults, orderbook, and
  pre-deposit contracts.

## Main Risks

- Maximum useful leverage is 40x BTC and 50x SPY, not 500x.
- Cross margin means one position can consume collateral intended for another;
  TICK should keep one isolated Trading Account per user/strategy while the V1
  product permits one active position.
- API and WebSocket reads require a Geomi bearer token; anonymous production
  reads currently return `401`.
- A separate Aptos account and key lifecycle must be added to TICK's current
  EVM/Solana wallet model.
- The public application defaults to as much as 8% maximum slippage on BTC;
  TICK must impose a much tighter route-specific limit.
- Official sub-second performance figures are venue claims. TICK has not yet
  measured request-to-commit, request-to-fill, WebSocket delivery, or close
  latency.
- Exact live market parameters and minimum ticket sizes still require an
  authenticated runtime snapshot.
- The public terms exclude US and Ontario residents, prohibit VPN-based
  circumvention, and contain broad automated-access and commercial-use clauses.
  Customer-facing TICK routing requires explicit legal/venue confirmation.
- API docs describe Builder Codes as permissionless while another developer
  summary mentions broker or affiliate approval. Revenue eligibility needs
  confirmation before relying on it.

## Canary Plan

Create a dedicated Aptos canary identity rather than reusing an operational
EVM or Solana wallet.

```text
1. Create a Geomi project, client API token, Node API token, and Gas Station.
2. Create one API Wallet and one Trading Account on Decibel mainnet.
3. Verify the API Wallet can place/cancel/close but cannot withdraw.
4. Deposit a bounded USDC amount into the Trading Account.
5. Snapshot all enabled markets, parameters, depth, fees, and minimum sizes.
6. Open and close one minimum-size BTC order at 40x using IOC.
7. Repeat one ETH order at 25x and one SPY order at 50x during market hours.
8. Place, trigger, and reconcile one native stop-loss canary.
9. Disconnect WebSocket during an order and prove REST/onchain backfill.
10. Withdraw the remaining collateral through the owner path.
```

Record:

```text
build_ms
sign_ms
submit_to_hash_ms
hash_to_aptos_commit_ms
commit_to_fill_event_ms
request_to_fill_ms
fill_to_private_ws_ms
fill_to_position_visible_ms
close_request_to_fill_ms
quoted_spread_bps
realized_slippage_bps
maker_taker_fee_usd
funding_usd
aptos_gas_usd
venue_account_delta
withdrawal_finalization_ms
```

The route should remain research-only until TICK has at least 20 complete
cycles, one stop, one liquidation or controlled liquidation-account test, one
restart/reconnect recovery, and a verified no-withdraw trading credential.

## Current TICK Role

Treat Decibel as a top signed-canary candidate for TICK Pro and broad market
coverage. It is likely to fill much faster than the current oracle-callback
venues, and its onchain CLOB provides strong execution truth.

Do not use it to replace the 500x consumer route. The useful product split is:

```text
gTrade / Avantis
  high-leverage oracle routes

Decibel
  fast 10x-50x onchain CLOB route across crypto and global markets
```

## Primary Sources

- [Trader overview](https://docs.decibel.trade/for-traders/overview)
- [Live BTC market](https://app.decibel.trade/trade/BTC-USD)
- [Market announcements](https://app.decibel.trade/announcements)
- [Fees](https://docs.decibel.trade/for-traders/fees)
- [Margin](https://docs.decibel.trade/for-traders/margin)
- [Liquidations](https://docs.decibel.trade/for-traders/liquidations)
- [Auto-deleveraging](https://docs.decibel.trade/for-traders/auto-deleveraging)
- [Core concepts](https://docs.decibel.trade/quickstart/concepts)
- [TypeScript starter kit](https://docs.decibel.trade/quickstart/typescript-starter-kit)
- [Gas Station](https://docs.decibel.trade/quickstart/gas-station)
- [REST authentication](https://docs.decibel.trade/api-reference/rest/authentication)
- [WebSocket overview](https://docs.decibel.trade/api-reference/websocket/overview)
- [WebSocket connection management](https://docs.decibel.trade/api-reference/websocket/connection)
- [Place order](https://docs.decibel.trade/developer-hub/on-chain/order-management/place-order)
- [Builder Codes](https://docs.decibel.trade/quickstart/builder-codes)
- [Audits](https://docs.decibel.trade/security/audits)
- [Terms of Service](https://decibel.trade/terms-of-service)
