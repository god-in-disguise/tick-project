# TICK MVP

Production-shaped MVP for TICK.

## Target Deployment

- Backend: DigitalOcean, Docker Compose first.
- Frontend: Vercel, PWA-first.
- Database: Postgres.
- Runtime cache/pubsub: Redis.
- Venue: gTrade/Gains first, venue-agnostic primitives.

## Backend Processes

The backend is one codebase with multiple process roles:

- `api` - FastAPI HTTP API and client event stream.
- `worker` - durable execution jobs and reconciliation.
- `market-feed` - price/feed ingestion and volatility scanner.
- `venue-events` - direct venue event listener and state observations.

Avoid microservices until the state model is stable.

## MVP Rules

- one live venue at first;
- one active position per user;
- one in-flight command per user;
- native venue stop required;
- open/close are idempotent;
- final PnL must reconcile;
- chart must use truthful market data only.

