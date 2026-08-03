# Paradex

Snapshot: 2026-08-03.

Evidence: documented and public measured; not live tested by TICK.

## Bottom Line

Paradex Retail is an unexpectedly strong small-ticket candidate. Interactive
orders are documented as zero fee and receive a 300 ms speed bump. That is a
reasonable trade for TICK if the full request-to-fill path remains fast and
the custodial PWA flow qualifies for the retail profile.

## Public Snapshot

TICK queried the official market endpoint on 2026-08-03:

```text
perpetual markets: 62
BTC/ETH/SOL maximum leverage from 2% initial margin: 50x
HYPE maximum leverage from 5% initial margin: 20x
minimum notional for these markets: $10
```

The current BTC market payload reports:

```text
interactive maker/taker fee: 0
API taker fee: 2 bps
```

The general Pro fee page lists a different base schedule. The connector must
query and store the account's effective fee rather than hardcode either value.

## Profiles

Paradex documents two relevant paths:

```text
Retail / interactive
  zero fees
  300 ms speed bump
  lower order-rate limits

Pro / API
  no retail speed bump
  API fee schedule
  higher operational limits
```

The documented retail limits are ample for a one-position consumer MVP, but
TICK must confirm that its request classification is allowed and stable.

## Integration Fit

- EVM onboarding into a Paradex/Stark account.
- Trading subkeys can be restricted from withdrawals and transfers.
- REST and private WebSocket order/fill lifecycle.
- Native market, limit, stop, TP, and SL orders.
- Fast public order-book streams.

## Main Risks

- Stark onboarding and key derivation add implementation complexity.
- The retail profile may depend on `token_usage=interactive` semantics that
  need explicit confirmation for TICK's backend-controlled wallets.
- Zero fee does not remove spread, slippage, funding, or liquidation risk.
- Fee documentation and market payloads currently need reconciliation.

## Canary

Test retail and API classification with the same $10 order. Record effective
fee, 300 ms delay, acknowledgement, fill, private event delivery, position
visibility, close, and final account balance.

## Primary Sources

- [Retail and Pro profiles](https://docs.paradex.trade/trading/trader-profiles)
- [Trading fees](https://docs.paradex.trade/trading/trading-fees)
- [API authentication](https://docs.paradex.trade/api/general-information/api-authentication)
- [Order types](https://docs.paradex.trade/trading/orders/placing-orders)
- [WebSocket API](https://docs.paradex.trade/ws/general-information/)

