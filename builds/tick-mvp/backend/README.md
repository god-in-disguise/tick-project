# Backend

Production MVP backend scaffold.

The local MVP proved the venue behavior. This backend should extract that behavior into durable primitives:

- `User`
- `AuthIdentity`
- `WalletAccount`
- `Asset`
- `TradeIntent`
- `ExecutionAttempt`
- `Position`
- `VenueEvent`
- `Reconciliation`
- `WalletAccount`
- `LedgerEvent`

The first real implementation should extract the gTrade connector from `../../local-mvp/tick-mvp-local/backend/connectors/` without copying local SQLite/threading assumptions.

## Product Decisions

- Auth is Google ID token login plus backend-issued TICK JWT.
- V1 wallets are platform-created Arbitrum wallets.
- Private keys are encrypted before storage in Postgres using `CUSTODY_PRIVATE_KEY_ENCRYPTION_KEY`.
- Users deposit Arbitrum USDC to their platform wallet.
- Withdrawals are automatic worker jobs after request validation.
- Users should not manage ETH. Platform/delegated gas is charged back in USDC through ledger events.
- gTrade is the first live venue, but tables and API contracts use venue-neutral primitives.

## Current Contract Pass

This scaffold currently implements the contract layer and Postgres persistence, but not live venue execution yet:

- `POST /api/auth/dev-session`
- `POST /api/auth/google`
- `GET /api/me`
- `GET /api/state`
- `GET /api/positions`
- `GET /api/wallet/deposit-address`
- `GET /api/wallet/withdrawals`
- `POST /api/wallet/withdrawals`
- `POST /api/trade/quote`
- `POST /api/trade/open`
- `POST /api/trade/close`

Auth is bearer-token based. For local development, `POST /api/auth/dev-session` returns a dependency-free HS256 JWT. Production login uses Google ID token verification and then returns the same backend-issued TICK session JWT.

Docker uses `TICK_STORE_BACKEND=postgres` and runs migrations from `migrations/001_core.sql` on startup. Local unit tests can still inject `MemoryStore` directly as a fast test double.

Verified local Docker smoke:

- API, Postgres, Redis, worker, market-feed, and venue-events start from Compose.
- `GET /health` and `GET /ready` return ok.
- dev session creates/reuses a user and platform Arbitrum wallet.
- deposit address returns the platform wallet.
- quote/open/close creates persisted quote, intent, execution attempt, position, and reconciliation rows.
- ARQ worker consumes queued open/close/withdrawal jobs.
- idempotency returns the original attempt for duplicate payloads.
- idempotent replays use deterministic ARQ job IDs, so the same execution is not queued twice.
- idempotency key reuse with a different payload returns conflict.
- one active position and one active close command are enforced at the API/store layer.

The execution worker currently acknowledges jobs only. The next real work is extracting gTrade quote/build/submit/event/reconcile primitives from `../../local-mvp/tick-mvp-local/backend/connectors/`.

## Package Layout

The code is layered for readability without turning the MVP into a framework project:

- `tick_mvp.api` - FastAPI app, HTTP routes, and session handling.
- `tick_mvp.domain` - Pydantic contracts and state machines.
- `tick_mvp.infrastructure` - storage and queue adapters.
- `tick_mvp.workers` - ARQ tasks plus long-running market/event service entrypoints.
- `tick_mvp.core` - runtime settings.

Root modules such as `tick_mvp.app` and `tick_mvp.schemas` are compatibility shims only.

Runtime shape follows the ARQ/FastAPI boilerplate pattern, but reduced to the pieces TICK needs:

- API process handles sessions, validation, and intent acceptance.
- ARQ worker process consumes execution jobs from Redis.
- Market-feed and venue-event processes remain separate long-running services.
- Docker Compose wires Postgres and Redis with healthchecks.

Run backend Compose from this directory:

```bash
docker compose up --build
```

Do not add venue execution directly to the API process. The next step is:

1. API accepts quote/open/close requests.
2. API persists intent/attempt records in Postgres.
3. API writes a durable outbox/job record in the same transaction.
4. Worker executes gTrade from the persisted attempt.
5. Venue/event workers append observations.
6. A single reducer mutates normalized position state.
