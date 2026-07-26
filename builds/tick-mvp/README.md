# TICK MVP

Production-shaped MVP for TICK.

## Target Deployment

- Backend: DigitalOcean, backend-owned Docker Compose first.
- Frontend: Vercel, PWA-first for fast sharing; mobile-shaped UX copied from the local Expo MVP.
- Database: Postgres.
- Runtime cache/pubsub: Redis.
- Venue: gTrade/Gains first, venue-agnostic primitives.
- Auth: Google ID token login, backend-issued TICK session JWT.
- Wallets: platform-created Arbitrum wallets with encrypted Postgres key material for MVP.

## Backend Processes

The backend is one codebase with multiple process roles:

- `api` - FastAPI HTTP API and client event stream.
- `worker` - durable execution jobs and reconciliation.
- `market-feed` - price/feed ingestion and volatility scanner.
- `venue-events` - direct venue event listener and state observations.

Avoid microservices until the state model is stable.

Backend runtime files live under `backend/`. The frontend is separate and should be deployed as a Vercel/PWA app, not as part of backend Compose.

The PWA is a distribution choice for the first deployable MVP. The product reference remains the local Expo live canary: one market, real chart, vertical open/close gesture, horizontal market switching while flat, net PnL, and clear close state.

## MVP Rules

- one live venue at first;
- one active position per user;
- one in-flight command per user;
- native venue stop required for real-money opening;
- open/close are idempotent;
- final PnL must reconcile;
- chart must use truthful market data only.
- users should not manage ETH gas;
- platform pays gas and records USDC gas charges.

## Current Implementation Status

- Backend scaffold runs with Docker Compose, Postgres, Redis, ARQ worker, market-feed process, and venue-events process.
- Auth/session, platform wallet creation, deposit address, quote, open intent, close intent, idempotency, and withdrawal contracts are wired.
- Open/close jobs are queued and consumed, but live gTrade execution has not yet been extracted into this backend.
- `builds/local-mvp/tick-mvp-local` and `builds/local-mvp/tick-mvp-local-expo` remain the live canary reference.
