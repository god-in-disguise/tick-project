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

- Private MVP auth uses invitation codes plus a backend-issued TICK JWT.
- Each invite receives an internal placeholder email until verified account linking is added.
- V1 wallets are platform-created Arbitrum wallets.
- Private keys are encrypted before storage in Postgres using `CUSTODY_PRIVATE_KEY_ENCRYPTION_KEY`.
- Users deposit Arbitrum USDC to their platform wallet.
- Users never need to deposit, hold, or understand ETH.
- Each user wallet delegates gTrade execution to TICK's platform execution agent.
- Normal opens and closes keep the user wallet as position owner while the platform agent signs and pays ETH gas.
- A dedicated platform gas wallet tops up user wallets only when one-time setup or a withdrawal needs the user wallet to sign.
- Confirmed setup, open, close, and withdrawal gas is converted through the Arbitrum Chainlink ETH/USD feed and reserved from the user's spendable USDC.
- Platform top-up and future treasury-sweep overhead is a TICK cost, not a user gas charge.
- Withdrawals are automatic worker jobs after request validation.
- Withdrawal signing persists encrypted raw transaction bytes before broadcast, so retries reuse the same nonce and transaction hash.
- gTrade is the first live venue, but tables and API contracts use venue-neutral primitives.

## Current Contract Pass

This scaffold currently implements the contract layer, Postgres persistence, live gTrade quotes, and a guarded worker execution path:

- `POST /api/auth/invite`
- `GET /api/me`
- `GET /api/state`
- `GET /api/events`
- `GET /api/positions`
- `GET /api/wallet/deposit-address`
- `GET /api/wallet/withdrawals`
- `POST /api/wallet/withdrawals`
- `POST /api/trade/quote`
- `POST /api/trade/open`
- `POST /api/trade/close`

Auth is bearer-token based. Every environment uses an invitation created in
Postgres, and successful redemption returns the normal TICK session JWT. Raw
invite codes are shown once and only their HMAC hashes are stored. An invite
creates one user and one wallet on first use, then restores that same account.

Create or rotate an invitation:

```bash
docker compose exec api python scripts/create_invite.py --name Chronos
```

The account uses an internal `@pending.tick.local` placeholder until verified
email linking is implemented.

Docker uses `TICK_STORE_BACKEND=postgres` and runs migrations from `migrations/001_core.sql` on startup. Local unit tests can still inject `MemoryStore` directly as a fast test double.

Verified local Docker smoke:

- API, Postgres, Redis, worker, market-feed, and venue-events start from Compose.
- `GET /health` and `GET /ready` return ok.
- invite redemption creates/reuses one user and platform Arbitrum wallet.
- deposit address returns the platform wallet.
- quote uses live gTrade pair metadata/pricing when `TICK_REAL_QUOTES_ENABLED=true`.
- BTCDEGEN quotes normalize to venue execution leverage and include estimated open/close costs, liquidation estimate, and stop-loss estimate.
- open/close creates persisted quote, intent, execution attempt, position, and reconciliation rows.
- ARQ worker consumes queued open/close/withdrawal jobs and returns dry-run execution results when `TICK_REAL_EXECUTION_ENABLED=false`.
- USDC withdrawals validate wallet state, exclude active positions, persist signed bytes before broadcast, recover by deterministic transaction hash, and append a confirmed ledger event.
- Gas top-ups persist the exact encrypted signed transaction before broadcast and safely retry the same hash/nonce.
- Wallet balance responses expose on-chain USDC, accrued gas charges, and spendable USDC; the compatibility `usdc` field is spendable USDC.
- Realized trade results include position-linked platform gas charges instead of overstating wallet PnL.
- idempotency returns the original attempt for duplicate payloads.
- idempotent replays use deterministic ARQ job IDs, so the same execution is not queued twice.
- idempotency key reuse with a different payload returns conflict.
- one active position, one active close command, and no position/withdrawal overlap are enforced at the API/store layer.

Live execution is behind `TICK_REAL_EXECUTION_ENABLED`. When enabled, the worker decrypts the user's platform wallet key for one-time delegation, allowance, and withdrawal operations. Normal gTrade opens and closes are wrapped in `delegatedTradingAction`, signed by the platform execution agent, and leave collateral, position ownership, and PnL on the user's wallet. Identical signed bytes race through the configured `ARB_RPC_URL` and Arbitrum's direct sequencer. The worker keeps both write transports warm, persistent providers, a process-wide sender nonce coordinator, allowance/delegate caches, a short-lived shared fee cache, fixed hot-path gas limits, and deterministic transaction hashes.

The worker keeps one direct Arbitrum callback stream and one normalized Gains
event stream for all active TICK users. Events are correlated by wallet, pair,
and venue position index. Direct callback logs are the normal fast path, the
normalized Gains stream is a fallback, and delayed `/open-trades` reads are
recovery. Close is committed when venue execution is observed; wallet PnL
reconciliation follows outside the exposure-critical path.

The quote endpoint also schedules wallet preparation before the gesture. This
background job observes balance, allowance, and delegate state, tracks the
wallet on the shared event stream, and completes missing one-time setup. It does
not hold the user's lock while merely reading ready state, and a normal
delegated open does not block on balance, allowance, or delegate RPC reads.
Known insufficient prepared balance still fails locally; otherwise the gTrade
contract remains the atomic collateral and permission validator. Market
metadata, live prices, and fee inputs are warmed at process level.

July 28 local delegated canary after removing preparation from the hot path:

- `$15` BTC/USD long at `100x`, `$2` venue stop, one-second hold.
- API acceptance: `23.7ms`.
- Connector wallet preparation: `2.0ms`.
- Transaction response: `1.10s`; receipt observed at `1.56s`.
- Direct gTrade open callback: `2.11s` from connector start.
- Position visible through a `100ms` polling canary: `2.28s`.
- Close visible: `2.67s` in this sample.
- User wallet paid no ETH; agent nonces were serialized process-wide.
- Venue cash flow and wallet reconciliation produced a final `-$1.305076`.

The first platform-agent version regressed visible open to `3.35s`. Removing
the blocking balance read and quote-preparation lock contention returned it to
`2.28s`, effectively the same as the previous direct-signing baseline
(`2.26s`). This was a regression fix, not a new protocol-speed improvement.
The remaining local latency is transaction transport/receipt propagation plus
the venue oracle callback, so deployed-region RPC measurements are required
before setting an SLO.

The worker also primes one explicit shared direct-sequencer TLS session at
startup and refreshes it every ten seconds. A cross-thread Docker check measured
`1.35s` for the cold connection and `198ms` when the broadcaster reused it.
This removes the first-open-after-idle transport penalty; it does not change
gTrade's oracle callback latency.

The PWA now includes USDC deposit QR/address, automatic withdrawals, spendable
balance, trade settings, and filtered history. It consumes an authenticated
server event stream for fast position-state changes with a slow HTTP recovery
poll.

The next hardening work is asynchronous treasury collection of reserved USDC
gas charges, deployment canaries for restart and ambiguous-broadcast recovery,
and external private-beta limits before this becomes a broad-public product.

## Package Layout

The code is layered for readability without turning the MVP into a framework project:

- `tick_mvp.api` - FastAPI app, HTTP routes, and session handling.
- `tick_mvp.domain` - Pydantic contracts and state machines.
- `tick_mvp.infrastructure` - storage and queue adapters.
- `tick_mvp.venues` - venue-specific market, quote, and transaction primitives.
- `tick_mvp.execution` - worker orchestration between persisted attempts and venue adapters.
- `tick_mvp.wallets` - chain-level deposit/withdrawal execution and recovery.
- `tick_mvp.workers` - ARQ tasks plus long-running market/event service entrypoints.
- `tick_mvp.core` - runtime settings.

Root modules such as `tick_mvp.app` and `tick_mvp.schemas` are compatibility shims only.

Runtime shape follows the ARQ/FastAPI boilerplate pattern, but reduced to the pieces TICK needs:

- API process handles sessions, validation, and intent acceptance.
- ARQ worker process consumes execution jobs from Redis.
- Market-feed and venue-event processes remain separate long-running services.
- Docker Compose wires Postgres and Redis with healthchecks.
- Signed Arbitrum writes race the configured RPC and direct sequencer using
  identical raw bytes; reads, receipts, and recovery remain on the configured
  provider.
- One worker process currently owns the shared platform-agent nonce stream.
  Multi-process execution requires agent sharding or a durable nonce lease
  before horizontal scaling.

The execution attempt stores its deterministic transaction hash and nonce
before either write request. Route winner and per-route response timings are
stored in the transaction result payload for canary comparison.

Run backend Compose from this directory:

```bash
docker compose up --build
```

Run the API canary from the repository root:

```bash
builds/local-mvp/tick-mvp-local/.venv/bin/python builds/tick-mvp/backend/scripts/backend_canary.py
```

The canary creates a dev session, gets the platform wallet deposit address and balances, asks for a live gTrade quote, accepts an open intent, waits for the position to become open, then accepts a close intent and waits for the terminal state. It cannot bypass `TICK_REAL_EXECUTION_ENABLED`; with real execution disabled, it should stop after the opening wait and print the current persisted state.

For local timing inspection, pass the Docker Postgres URL:

```bash
builds/local-mvp/tick-mvp-local/.venv/bin/python builds/tick-mvp/backend/scripts/backend_canary.py \
  --db-url postgresql://tick:tick@127.0.0.1:5432/tick
```

To bind a funded dev wallet to a local dev user:

```bash
docker compose exec -e DEV_WALLET_PRIVATE_KEY=0x... api \
  python scripts/import_dev_wallet.py --user-id funded-dev
```

Do not add venue execution directly to the API process. The next step is:

1. API accepts quote/open/close requests.
2. API persists intent/attempt records in Postgres.
3. API writes a durable outbox/job record in the same transaction.
4. Worker executes gTrade from the persisted attempt.
5. Venue/event workers append observations.
6. A single reducer mutates normalized position state.
