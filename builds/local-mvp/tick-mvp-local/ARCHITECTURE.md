# Local Canary Architecture

The local canary uses the same ownership boundaries intended for the real backend without adding production infrastructure prematurely.

```text
Expo client
  -> FastAPI normalized API
    -> ExecutionService
      -> VenueConnector
        -> GTradeConnector
    -> MarketService
    -> TickService
    -> LocalStore (SQLite)
```

## Connector Boundary

`backend/connectors/base.py` defines the venue contract:

- account and positions
- markets, prices, and chart history
- opening and closing estimates
- opening and closing execution
- permission/allowance preparation

`gtrade_connector.py` is the current live canary adapter. The supporting gTrade modules own pricing, delegated wallet mechanics, callback/event decoding, public backend reads, and latency measurements.

Ostium modules remain in the local MVP as earlier venue research and cross-asset reference code, not as the current primary route.

Any future `AsterConnector`, `LighterConnector`, or `OstiumConnector` should implement the same interface and be registered in `backend/registry.py`. It must not duplicate quote expiry, idempotency, one-position enforcement, persistence, or mobile state handling; those belong to `ExecutionService`.

## Execution Ownership

The connector reports venue facts. `ExecutionService` owns TICK facts:

- one-position rule
- short-lived quote validation
- idempotency
- `created/opening/open/closing/closed/failed/unknown`
- background submission and reconciliation
- restart recovery
- completed one-wallet result

## Local Versus Production

SQLite, one process, and one wallet are deliberate local choices. The real build can replace `LocalStore` with Postgres and move workers out of process without changing the connector or mobile API contract.

The closest product reference is the Expo loop:

- real gTrade/Gains price feed
- one active chart
- swipe up/down to open
- same-direction swipe to close
- horizontal swipe only while flat
- real net PnL and final result
- native stop-loss support
- timestamp-based truthful chart rendering
