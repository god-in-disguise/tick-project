# TICK MVP

Production-shaped MVP for TICK.

## Target Deployment

- Backend: DigitalOcean, backend-owned Docker Compose first.
- Frontend: Vercel, PWA-first for fast sharing; mobile-shaped UX copied from the local Expo MVP.
- Database: Postgres.
- Runtime cache/pubsub: Redis.
- Venue: gTrade/Gains first, venue-agnostic primitives.
- Auth: invitation-code login and backend-issued TICK session JWT.
- Wallets: platform-created Arbitrum wallets with encrypted Postgres key material for MVP.

## Backend Processes

The backend is one codebase with multiple process roles:

- `api` - FastAPI HTTP API, one shared market feed, retained bars, and client event stream.
- `worker` - durable execution jobs and reconciliation.
- `venue-events` - direct venue event listener and state observations.

V1 runs exactly one API replica because that process owns the shared market
feed and history writer. Moving feed ownership to a separate process is required
before scaling the API horizontally.

Avoid microservices until the state model is stable.

Backend runtime files live under `backend/`. The frontend is separate and should be deployed as a Vercel/PWA app, not as part of backend Compose.

The PWA is a distribution choice for the first deployable MVP. The product reference remains the local Expo live canary: one market, real chart, vertical open/close gesture, horizontal market switching while flat, net PnL, and clear close state.

## MVP Rules

- one live venue at first;
- one active position per user;
- one in-flight command per user;
- optional stop and take-profit orders must be placed at the venue;
- open/close are idempotent;
- final PnL must reconcile;
- chart must use truthful market data only.
- users should not manage ETH gas;
- platform pays gas and records USDC gas charges.

## Current Implementation Status

- Backend runs with Docker Compose, Postgres, Redis, one API-owned market feed,
  an ARQ worker, and a venue-events process.
- Real delegated gTrade open/close execution is extracted and live-tested.
  The user wallet owns collateral and the position; TICK's platform agent pays
  Arbitrum gas.
- invite/session JWTs, per-user encrypted wallets, USDC deposits, automatic
  withdrawals, idempotent trade intents, venue-native SL/TP, terminal events,
  and final wallet reconciliation are wired.
- Platform gas is converted to USDC and included in the final per-position net
  result. The app holds a terminal result in `finalizing` until that charge is
  in the ledger.
- The PWA preserves the local Expo loop: real 60 FPS canvas tape, vertical
  open gestures, horizontal market switching, live net PnL, wallet actions,
  scanner, and filtered history.
- A normal browser shows an install landing. The trading product opens only in
  standalone PWA mode, with `?app=1` available for development preview.
- DigitalOcean backend and Vercel frontend deployment definitions are present
  under `deploy/`.
