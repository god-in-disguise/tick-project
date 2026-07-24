# TICK MVP

Production-shaped MVP for TICK.

## Target Deployment

- Backend: DigitalOcean, backend-owned Docker Compose first.
- Frontend: Vercel, PWA-first.
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

## MVP Rules

- one live venue at first;
- one active position per user;
- one in-flight command per user;
- native venue stop required;
- open/close are idempotent;
- final PnL must reconcile;
- chart must use truthful market data only.
- users should not manage ETH gas;
- platform pays gas and records USDC gas charges.
