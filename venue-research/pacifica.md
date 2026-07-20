# Pacifica

Snapshot: 2026-07-13.

Status: public API measured; signed trading not yet tested by TICK.

## Bottom Line

Pacifica is currently the easiest next venue to test for TICK's fast crypto loop. It exposes signed REST and WebSocket trading, supports isolated margin per symbol, accepts client order IDs, and lets an agent key trade without exposing the root Solana wallet key to the backend.

The code is straightforward. The real gates are Pacifica account access, a funded Solana account, and measured signed-order latency. Do not infer execution speed from public price requests.

## How It Works

- A Solana wallet owns the Pacifica account and deposits Solana USDC.
- Pacifica operates a hybrid order-book exchange with REST and WebSocket APIs.
- Signed requests use Ed25519 signatures.
- A user can bind an API agent wallet. The backend signs with the agent key while requests still identify the original account.
- Cross and isolated margin are supported per symbol. Margin mode cannot change while that symbol has an open position.
- Market orders support `client_order_id`, `reduce_only`, slippage limits, a builder code, and optional TP/SL.
- Pacifica documents an intentional approximately 200 ms delay on market orders to protect liquidity providers.

For TICK, the root wallet should authorize and fund the account. The execution service should hold only a scoped agent key. The exact agent permission boundary, especially withdrawal capability, must be verified before production.

Account state must be event-driven. Pacifica says `account_positions` and `account_orders` snapshots may lag under load; `account_trades` and `account_order_updates` are the real-time channels, while snapshots are for initialization and reconciliation.

## Access And Funds

- Minimum USDC deposit is currently `$10`; Pacifica charges network gas only.
- Minimum USDC withdrawal is `$1`; the documented withdrawal fee is `$1`.
- Pacifica is still described as Closed Beta and documents account-level deposit/withdrawal limits.
- Its documentation prohibits trading from a non-exhaustive list of restricted jurisdictions including the United States, Cuba, Crimea including Sevastopol, Iran, Afghanistan, Syria, and North Korea, with IP enforcement.
- Pacifica documents a hot/cold fund architecture: the matching engine controls a limited hot withdrawal wallet, while most funds sit in Squads-governed cold vaults.

Operationally, TICK should model Pacifica as a venue account whose balances and positions must be reconciled, not as assets that remain in the user's wallet during each trade.

## Current Market Snapshot

TICK queried `GET https://api.pacifica.fi/api/v1/info` on 2026-07-13:

```text
69 instruments total
68 perpetuals
1 spot market

50x: BTC, ETH, USDJPY, EURUSD
20x: SOL, XRP, HYPE, DOGE, BNB, SP500
10x: 43 instruments, including crypto, stocks, metals, energy, and indices
5x: 9 instruments
3x: 6 instruments
```

BTC and ETH currently have a `$10` minimum order size and 50x maximum leverage. Pacifica reports 65+ perpetual markets and approximately `$1B` daily volume; those are Pacifica's own figures and must not replace independent liquidity measurements.

## Capacity At TICK Size

The same public market-info response reported a `$5,000,000` maximum order size for both BTC and ETH. This is an API order limit, not a promise that every order of that size will fill and not necessarily a maximum-position limit.

TICK also measured public order-book snapshots on 2026-07-13:

```text
BTC spread: about 0.16 bps
BTC visible within 1 bp: about $218k asks / $119k bids
BTC visible within 2 bps: about $436k asks / $317k bids

ETH spread: about 0.56 bps
ETH visible within 1 bp: about $199k asks / $50k bids
ETH visible within 2 bps: about $338k asks / $189k bids
```

In a second snapshot, simulated public-book VWAP impact remained below 0.6 bps through `$100,000` notional on both BTC and ETH. These are point-in-time public measurements, not signed fill guarantees.

```text
$10 margin at 50x =   $500 notional
$20 margin at 50x = $1,000 notional
$50 margin at 50x = $2,500 notional
```

Supply is therefore not a concern for TICK-sized BTC/ETH orders. Pacifica's limitation for this product is the 50x leverage ceiling and 4 bps taker fee, not order-book capacity.

## Cost

Entry fee tier:

```text
maker: 0.015%
taker: 0.040%
```

For two taker fills, the simplified round-trip fee is 0.08% of notional before spread, slippage, funding, and builder fees.

```text
50x: about 4.0% of margin
20x: about 1.6% of margin
10x: about 0.8% of margin
```

This is materially cleaner for TICK's short holds than a route whose fee consumes roughly 10% of margin at 100x. Pacifica caps BTC and ETH at 50x, so it cannot provide a 100x BTC/ETH preset.

## Latency

Public measured from Moscow on 2026-07-13:

```text
new HTTPS connection to public prices: about 0.78 s
reused HTTPS connection: about 0.39-0.63 s
```

This is only public REST latency from a developer laptop. It is not order latency. TICK should use a persistent WebSocket connection and deploy the execution service near Pacifica's API infrastructure.

Signed latency remains unknown. The first canary must separately measure:

```text
client request -> API acknowledgement
acknowledgement -> account trade event
trade event -> position event/snapshot
close request -> close fill
close fill -> final account reconciliation
```

The realistic target is a sub-second visible open/close from a well-placed backend, but that is a hypothesis until measured. The documented 200 ms market-order delay is a floor inside the venue path, not a total-latency promise.

## Points And Builder Upside

- Pacifica currently documents 10,000,000 points distributed weekly.
- Organic GUI and API trading can qualify.
- The formula is intentionally dynamic and opaque.
- Self-trading, sybil activity, and manipulative trading do not qualify.
- Pacifica also documents up to 10,000,000 points allocated to meaningful builder contributions.
- Builder-coded orders require user approval and can carry an additional approved builder fee.

Points have no guaranteed token conversion or TGE value in the documentation. Treat them as uncertain upside, never as compensation for worse execution.

## Testing Difficulty

Estimated effort once account access and funds exist:

```text
public market/price collector:       1-2 hours
signed test harness:                 half a day
TICK connector happy path:           1-2 focused days
production connector and recovery:   2-4 focused days
```

The official Python repository is an examples collection rather than a mature packaged SDK. That is sufficient: signing is small and deterministic, and TICK should own a thin connector rather than depend heavily on an immature package.

The existing `WALLET_PK` is an EVM key for Ostium and cannot be reused. A Pacifica canary requires a Solana Ed25519 account and agent key. No Pacifica secret is currently configured in the project environment.

## First Signed Canary

1. Confirm account access and regional eligibility.
2. Deposit the minimum Solana USDC needed for a small isolated canary.
3. Bind a new test-only agent wallet to the root account.
4. Connect persistent market, trade, order-update, and position streams.
5. Set BTC to isolated margin and an allowed leverage, initially 25x or 50x.
6. Submit a small market order with a UUID `client_order_id` and strict expiry/slippage policy.
7. Mark the position open only from the account trade/order event.
8. After confirmation, submit a reduce-only market close.
9. Reconcile fills, fees, realized PnL, position state, and account balance through REST snapshots.
10. Repeat under reconnect, duplicate-request, stale-price, and rejected-order cases.

## Open Questions

- Can the test account access mainnet without an invite or access code?
- Which backend region gives the best stable WS latency?
- What is the exact agent-key permission and revocation model?
- How far can account position snapshots lag behind event streams under load?
- What are real BTC/ETH spread, slippage, and fill rates for `$10-$50` market orders?
- Is builder-points allocation still accepting new teams, and what contribution threshold applies?
- Which jurisdictions and user classifications can TICK legally route to Pacifica?

## Primary Sources

- [Pacifica overview](https://docs.pacifica.fi/pacifica/readme)
- [Trading access overview](https://docs.pacifica.fi/trading-on-pacifica/overview)
- [Fund security model](https://docs.pacifica.fi/trading-on-pacifica/fund-security)
- [Deposits and withdrawals](https://docs.pacifica.fi/trading-on-pacifica/deposits-and-withdrawals)
- [Trading fees](https://docs.pacifica.fi/trading-on-pacifica/trading-fees)
- [Margin and leverage](https://docs.pacifica.fi/trading-on-pacifica/margin-and-leverage)
- [API agent keys](https://docs.pacifica.fi/api-documentation/api/signing/api-agent-keys)
- [WebSocket market orders](https://docs.pacifica.fi/api-documentation/api/websocket/trading-operations/create-market-order)
- [WebSocket order book](https://docs.pacifica.fi/api-documentation/api/websocket/subscriptions/orderbook)
- [Delayed snapshot guidance](https://docs.pacifica.fi/api-documentation/api/api-faq/delayed-account_positions)
- [Points program](https://docs.pacifica.fi/programs/points-program)
- [Builder program](https://docs.pacifica.fi/programs/builder-program)
- [Official Python examples](https://github.com/pacifica-fi/python-sdk)
