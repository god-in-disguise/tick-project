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

The first gTrade extraction is now started. The backend has live gTrade quote support and a worker-side execution adapter, while live trading remains disabled unless explicitly enabled.

## Product Decisions

- Auth is Google ID token login plus backend-issued TICK JWT.
- V1 wallets are platform-created Arbitrum wallets.
- Private keys are encrypted before storage in Postgres using `CUSTODY_PRIVATE_KEY_ENCRYPTION_KEY`.
- Users deposit Arbitrum USDC to their platform wallet.
- Withdrawals are automatic worker jobs after request validation.
- Users should not manage ETH. Platform/delegated gas is charged back in USDC through ledger events.
- gTrade is the first live venue, but tables and API contracts use venue-neutral primitives.

## Current Contract Pass

This scaffold currently implements the contract layer, Postgres persistence, live gTrade quotes, and a guarded worker execution path:

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
- quote uses live gTrade pair metadata/pricing when `TICK_REAL_QUOTES_ENABLED=true`.
- BTCDEGEN quotes normalize to venue execution leverage and include estimated open/close costs, liquidation estimate, and stop-loss estimate.
- open/close creates persisted quote, intent, execution attempt, position, and reconciliation rows.
- ARQ worker consumes queued open/close/withdrawal jobs and returns dry-run execution results when `TICK_REAL_EXECUTION_ENABLED=false`.
- idempotency returns the original attempt for duplicate payloads.
- idempotent replays use deterministic ARQ job IDs, so the same execution is not queued twice.
- idempotency key reuse with a different payload returns conflict.
- one active position and one active close command are enforced at the API/store layer.

Live execution is behind `TICK_REAL_EXECUTION_ENABLED`. When enabled, the worker decrypts the user's platform wallet key, auto-approves USDC if needed, signs from that user wallet, submits through the configured `ARB_RPC_URL`, waits for gTrade position visibility/absence, and updates the execution/position rows. It keeps the useful local-MVP speed work: persistent provider, cached nonces, short-lived fee cache, fixed hot-path gas limits, and deterministic tx hash before broadcast.

The next hardening work is direct callback-event journaling, recovery after ambiguous RPC responses, and final PnL reconciliation.

## Package Layout

The code is layered for readability without turning the MVP into a framework project:

- `tick_mvp.api` - FastAPI app, HTTP routes, and session handling.
- `tick_mvp.domain` - Pydantic contracts and state machines.
- `tick_mvp.infrastructure` - storage and queue adapters.
- `tick_mvp.venues` - venue-specific market, quote, and transaction primitives.
- `tick_mvp.execution` - worker orchestration between persisted attempts and venue adapters.
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

Run the API canary from the repository root:

```bash
builds/local-mvp/tick-mvp-local/.venv/bin/python builds/tick-mvp/backend/scripts/backend_canary.py
```

The canary creates a dev session, gets the platform wallet deposit address, asks for a live gTrade quote, accepts an open intent, waits for the position to become open, then accepts a close intent and waits for the terminal state. It cannot bypass `TICK_REAL_EXECUTION_ENABLED`; with real execution disabled, it should stop after the opening wait and print the current persisted state.

For local timing inspection, pass the Docker Postgres URL:

```bash
builds/local-mvp/tick-mvp-local/.venv/bin/python builds/tick-mvp/backend/scripts/backend_canary.py \
  --db-url postgresql://tick:tick@127.0.0.1:5432/tick
```

Do not add venue execution directly to the API process. The next step is:

1. API accepts quote/open/close requests.
2. API persists intent/attempt records in Postgres.
3. API writes a durable outbox/job record in the same transaction.
4. Worker executes gTrade from the persisted attempt.
5. Venue/event workers append observations.
6. A single reducer mutates normalized position state.
