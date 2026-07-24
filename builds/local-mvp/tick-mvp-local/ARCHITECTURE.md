# Local Canary Architecture

The local canary uses the same ownership boundaries intended for the real backend without adding production infrastructure prematurely.

```text
Expo client
  -> FastAPI normalized API
    -> ExecutionService
      -> VenueConnector
        -> OstiumConnector
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
- allowance preparation

`ostium_connector.py` is the public Ostium adapter. `ostium_pricing.py` owns Ostium fee and liquidation estimates. `ostium_client.py` contains private contract, RPC, builder API, and subgraph mechanics.

An `AsterConnector` should implement the same interface and be registered in `backend/registry.py`. It must not duplicate quote expiry, idempotency, one-position enforcement, persistence, or mobile state handling; those belong to `ExecutionService`.

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
