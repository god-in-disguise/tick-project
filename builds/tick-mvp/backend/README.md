# Backend

Production MVP backend scaffold.

The local MVP proved the venue behavior. This backend should extract that behavior into durable primitives:

- `TradeIntent`
- `ExecutionAttempt`
- `Position`
- `VenueEvent`
- `Reconciliation`
- `WalletAccount`
- `LedgerEvent`

The first real implementation should extract the gTrade connector from `../../local-mvp/tick-mvp-local/backend/connectors/` without copying local SQLite/threading assumptions.

## Current Contract Pass

This scaffold currently implements the contract layer only:

- `POST /api/auth/dev-session`
- `GET /api/state`
- `GET /api/positions`
- `POST /api/trade/quote`
- `POST /api/trade/open`
- `POST /api/trade/close`

Auth is bearer-token based. For local development, `POST /api/auth/dev-session` returns a dependency-free HS256 JWT. Production can replace this with Privy verification while keeping the same user-session contract.

The current store is in-memory so frontend wiring and API shape can move quickly. The durable Postgres target schema is in `migrations/001_core.sql`.

Do not add venue execution directly to the API process. The next step is:

1. API accepts quote/open/close requests.
2. API persists intent/attempt records in Postgres.
3. Worker executes gTrade.
4. Venue/event workers append observations.
5. A single reducer mutates normalized position state.
